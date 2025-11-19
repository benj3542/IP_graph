import os
import json
import re
import networkx as nx
from tqdm import tqdm

# ---------- CONFIG ----------
input_folder = "/Users/benjaminfazal/Desktop/Skole/Kandidat/Semester_4/SocialGraph/final_proj/wiki_foreign_relations_jsons"

# ---------- LOAD DATA ----------
wiki_data = {}
for file in os.listdir(input_folder):
    if not file.endswith(".json"):
        continue
    with open(os.path.join(input_folder, file), "r", encoding="utf-8") as f:
        text = json.load(f)

    country = re.sub(r"Foreign[_ ]relations[_ ]of[_ ]", "", file.replace(".json", ""), flags=re.IGNORECASE)
    country = country.replace("_", " ").strip()
    wiki_data[country] = text

countries = list(wiki_data.keys())

# ---------- HELPERS ----------
def clean_wikitext(text: str) -> str:
    """Remove common MediaWiki markup and artifacts before sentence splitting."""
    # Remove references and HTML tags
    text = re.sub(r"<ref[^>]*>.*?</ref>", " ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)  # remove other HTML tags

    # Remove tables and templates ({{ }})
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)  # twice to catch nested ones

    # Remove file and image links
    text = re.sub(r"\[\[File:[^\]]+\]\]", " ", text)
    text = re.sub(r"\[\[Image:[^\]]+\]\]", " ", text)

    # Remove wiki links but keep readable text (e.g., [[Denmark|Danish]] → Danish)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)

    # Remove pipes, table symbols, bullets
    text = re.sub(r"[\|\*#]+", " ", text)

    # Remove URLs
    text = re.sub(r"http\S+", " ", text)

    # Remove extra braces and categories
    text = re.sub(r"\{\{|\}\}|\[\[Category:[^\]]+\]\]", " ", text)

    # Normalize whitespace and punctuation
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" .", ".").replace(" ,", ",")

    # Remove lingering non-textual symbols
    text = re.sub(r"[;•<>]+", " ", text)

    return text.strip()

def flatten_table_text(text: str) -> str:
    """
    Converts wiki-table markup into plain text sentences.
    Each '|-' or '|' row becomes its own line; '*' bullets become separate sentences.
    """
    # Split table rows and keep textual parts
    text = re.sub(r"\|\-", ". ", text)
    text = re.sub(r"^\|", "", text, flags=re.MULTILINE)
    text = text.replace("||", ". ")
    text = text.replace("|", ". ")
    text = text.replace("* ", ". ")
    text = re.sub(r"\s*\.\s*\.\s*", ". ", text)  # remove stacked dots
    return text

def extract_section(text):
    """Get the relevant section (Bilateral or Diplomatic relations) or fallback to full."""
    m = re.search(r"(?i)(==\s*(Bilateral relations|Diplomatic relations)\s*==)", text)
    return text[m.start():] if m else text

def sent_tokenize(text):
    """Simple sentence splitter."""
    text = re.sub(r"\s+", " ", text)
    sents = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sents if s.strip()]

# simpler phrase list
EMBASSY_PHRASES = [
    "has an embassy in",
    "is represented in",
    "is accredited to"
]

def is_embassy_sentence(sentence, country):
    """Checks if sentence starts with given country and has embassy phrase."""
    if not sentence.lower().startswith(country.lower()):
        return False
    return any(p in sentence.lower() for p in EMBASSY_PHRASES)

def is_shared_org_sentence(sentence):
    return "both countries are" in sentence.lower() and "member" in sentence.lower()

# ---------- GRAPH ----------
G = nx.Graph()
G.add_nodes_from(countries)

print(f"Loaded {len(countries)} countries")

embassy_pairs_found = 0
full_triples_found = 0

for src_country, raw_text in tqdm(wiki_data.items(), desc="Building embassy/org graph"):
    section = extract_section(raw_text)
    section = clean_wikitext(section)
    section = flatten_table_text(section)
    sents = sent_tokenize(section)


    for i, s1 in enumerate(sents):
        # Sentence 1 must start with the current country and mention embassy/representation
        if not is_embassy_sentence(s1, src_country):
            continue

        # Sentence 2 check: next few sentences for another country with embassy phrase
        for j in range(i + 1, min(i + 4, len(sents))):
            s2 = sents[j]
            for tgt_country in countries:
                if tgt_country == src_country:
                    continue
                if is_embassy_sentence(s2, tgt_country):
                    weight = 0.5
                    embassy_pairs_found += 1

                    # Sentence 3: within next 3 sentences, check if "Both countries are members"
                    if any(is_shared_org_sentence(x) for x in sents[j + 1:j + 4]):
                        weight = 1.0
                        full_triples_found += 1

                    if G.has_edge(src_country, tgt_country):
                        G[src_country][tgt_country]["weight"] = max(G[src_country][tgt_country]["weight"], weight)
                    else:
                        G.add_edge(src_country, tgt_country, weight=weight)
                    break  # stop checking once we match target
            else:
                continue
            break  # move on to next sentence once matched

print(f"Graph: {len(G.nodes())} nodes, {len(G.edges())} edges")
print(f"Embassy pairs found: {embassy_pairs_found}")
print(f"Full triples (embassy + shared org): {full_triples_found}")

nx.write_gexf(G, "foreign_relations_graph_simple_embassy_org.gexf")
print(" Saved: foreign_relations_graph_simple_embassy_org.gexf")

# visualize a weighted graph
# import matplotlib.pyplot as plt
# from matplotlib import cm
# pos = nx.spring_layout(G, seed=42)
# weights = [G[u][v]['weight'] for u, v in G.edges()]
# nx.draw(G, pos, with_labels=True, node_size=500, font_size=8,
#         width=[w * 2 for w in weights], edge_color=weights, edge_cmap=cm.viridis)
# plt.show()
