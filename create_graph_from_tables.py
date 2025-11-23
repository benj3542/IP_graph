"""
Create a network graph from Wikipedia Foreign Relations articles.

This script parses wikitables from Foreign Relations Wikipedia pages (stored as JSON files)
to extract diplomatic relationships between countries. An edge is created between two
countries if:

1. EMBASSY CONDITION: Both countries have embassies in each other's capitals
   - Checked by looking for bullet points like "Country A has an embassy in [City in B]"
   
2. ALLIANCE CONDITION (optional): Both countries are members of the same organization
   - Checked by looking for phrases like "Both countries are members of [Organization]"

The REQUIRE_ALLIANCE flag controls whether both conditions must be met:
- True: Only create edges where BOTH embassy AND alliance conditions are met (weight=1.0)
- False: Create edges if embassies exist, with weight=0.5 for embassy-only, 1.0 for both

Output: GEXF graph file with weighted edges

Author: Created for Social Graphs project
Date: November 2025
"""

import os
import json
import re
import networkx as nx
from tqdm import tqdm

# ---------- CONFIG ----------
input_folder = "/Users/smilladue/Desktop/Documents/DTU/social-graphs/IP_graph/wiki_foreign_relations_jsons"

# Flag to control edge requirements
REQUIRE_ALLIANCE = False  # Set to False to create edges based on embassies only

# Debug flag
DEBUG = False  # Set to False to disable debug output
DEBUG_COUNTRY = "Denmark"  # Which country to debug
DEBUG_DETAILED = False  # Show embassy and alliance detection details

# ---------- LOAD DATA ----------
print("Loading JSON files...")
wiki_data = {}
for file in os.listdir(input_folder):
    if not file.endswith(".json"):
        continue
    with open(os.path.join(input_folder, file), "r", encoding="utf-8") as f:
        text = json.load(f)
    
    # Skip disambiguation pages (they just redirect to other pages)
    if '{{Disambig}}' in text or '{{disambiguation}}' in text:
        continue
    
    # Extract country name from filename: "Foreign relations of CountryName.json"
    country = re.sub(r"Foreign[_ ]relations[_ ]of[_ ]", "", file.replace(".json", ""), flags=re.IGNORECASE)
    
    # Clean up special cases
    # "Georgia _country_" -> "Georgia"
    country = re.sub(r'\s*_country_\s*', '', country, flags=re.IGNORECASE)
    country = country.replace("_", " ").strip()
    wiki_data[country] = text

countries = list(wiki_data.keys())
print(f"Loaded {len(countries)} countries")

# ---------- HELPER FUNCTIONS ----------

def normalize_country_name(country):
    """
    Normalize country names for comparison.
    Handles "the X" vs "X" differences.
    """
    if not country:
        return None
    
    country = country.strip()
    
    # Create mapping for countries with "the" prefix
    # Store both versions to handle matching in either direction
    if country.lower().startswith('the '):
        # Return version without "the" for comparison
        return country[4:].strip()
    
    return country


def extract_country_name_from_flag(flag_text):
    """
    Extract country name from {{flag|CountryName}} or {{Flag|CountryName}}
    Also handles {{#invoke:flag||CountryName}} format used in some Wikipedia pages
    """
    # Try standard format: {{flag|CountryName}}
    match = re.search(r'\{\{[Ff]lag\|([^}|]+)', flag_text)
    if match:
        country = match.group(1).strip()
        return country
    
    # Try invoke format: {{#invoke:flag||CountryName}}
    match = re.search(r'\{\{#invoke:flag\|\|([^}|]+)', flag_text, re.IGNORECASE)
    if match:
        country = match.group(1).strip()
        return country
    
    return None


def find_bilateral_tables(text):
    """
    Find all wikitable sections, focusing on bilateral relations tables.
    Returns list of (table_text, start_pos) tuples.
    """
    tables = []
    
    # Pattern for wikitables - they start with {| and end with |}
    # We need to be careful with nested braces
    table_starts = []
    for match in re.finditer(r'\{\| class="wikitable[^"]*"', text):
        table_starts.append(match.start())
    
    for start in table_starts:
        # Find the matching closing |}
        depth = 0
        i = start
        while i < len(text):
            if text[i:i+2] == '{|':
                depth += 1
                i += 2
            elif text[i:i+2] == '|}':
                depth -= 1
                if depth == 0:
                    tables.append((text[start:i+2], start))
                    break
                i += 2
            else:
                i += 1
    
    return tables


def parse_wikitable_rows(table_text):
    """
    Parse a wikitable and extract rows.
    Returns list of row dictionaries with 'country', 'date', 'notes' keys.
    
    Wiki tables have format:
    |-
    |valign="top"
    |{{flag|Country}}||{{dts|date}}||Notes here
    *Additional notes on new lines
    """
    rows = []
    
    # Split by row delimiters (|- marks new row)
    row_sections = re.split(r'\n\|-', table_text)
    
    for row_section in row_sections[1:]:  # Skip header
        if not row_section.strip() or row_section.strip().startswith('!'):
            continue
        
        # Find the line with data (starts with | and contains {{flag)
        lines = row_section.split('\n')
        data_line = None
        data_line_idx = -1
        
        for idx, line in enumerate(lines):
            line_stripped = line.strip()
            # Check for both {{flag and {{#invoke:flag formats
            # The line might just be attributes like "valign=top", so also check if it contains a flag
            if ('{{flag' in line.lower() or '{{#invoke:flag' in line.lower()):
                # This line contains a flag template
                if line_stripped.startswith('|'):
                    data_line = line_stripped
                    data_line_idx = idx
                    break
        
        if not data_line:
            continue
        
        # Remove leading |
        if data_line.startswith('|'):
            data_line = data_line[1:]
        
        # Extract country from the line before splitting by ||
        # This handles cases like {{#invoke:flag||Algeria}} where || appears inside the template
        country = extract_country_name_from_flag(data_line)
        if not country:
            continue
        
        # Handle two table formats:
        # Format 1: Columns on same line with || separator: |{{flag|Country}}||Date||Notes
        # Format 2: Columns on separate lines with | prefix: 
        #   |{{flag|Country}}
        #   |Date
        #   |Notes
        
        notes_parts = []
        
        if '||' in data_line:
            # Format 1: Double-pipe separator
            columns = data_line.split('||')
            
            if len(columns) < 2:
                continue
            
            # Notes are in the last column (3rd column if present, else 2nd column)
            if len(columns) >= 3:
                notes_parts.append(columns[2])
            elif len(columns) >= 2:
                notes_parts.append(columns[1])
        else:
            # Format 2: Single-pipe on separate lines
            # Find all lines starting with | after the flag line
            # Typically: |number |{{flag|Country}} |Date |Notes
            # Notes could be on the 3rd or 4th | line depending on if there's a number column
            
            # Collect all | lines after the flag line
            column_lines = []
            for idx in range(data_line_idx + 1, len(lines)):
                line = lines[idx].strip()
                if not line:
                    continue
                if line.startswith('|-'):
                    break
                if line.startswith('|') and not line.startswith('||'):
                    column_lines.append(line[1:].strip())  # Remove leading |
                elif not line.startswith('|'):
                    # This might be a continuation line (bullet point)
                    if column_lines:  # Only add if we've found at least one column
                        notes_parts.append(line)
            
            # The first column line after the flag is usually the date
            # Any remaining column lines or non-column lines are notes
            if len(column_lines) >= 2:
                # Use the 2nd column onwards as notes
                notes_parts.extend(column_lines[1:])
            elif len(column_lines) == 1:
                # Just one more column (date), check for continuation lines
                pass  # notes_parts already has continuation lines
        
        # Add any continuation lines that follow (bullet points, additional notes)
        if data_line_idx >= 0 and data_line_idx + 1 < len(lines):
            for line in lines[data_line_idx + 1:]:
                line = line.strip()
                if line.startswith('|-'):
                    break
                # Skip lines we already processed as columns
                if line.startswith('|') and '||' not in data_line:
                    continue  # Already processed above for Format 2
                if line and not line.startswith('|'):
                    notes_parts.append(line)
        
        notes = '\n'.join(notes_parts)
        
        rows.append({
            'country': country,
            'notes': notes
        })
    
    return rows


def has_mutual_embassies(notes, source_country, target_country):
    """
    Check if the notes indicate both countries have embassies in each other.
    Returns True if both conditions met:
    - source_country has embassy in target_country
    - target_country has embassy in source_country
    
    The notes typically have bullet points like:
    * CountryA has an embassy in [CityInCountryB]
    * CountryB has an embassy in [CityInCountryA]
    
    Important: The subject (country having the embassy) comes BEFORE "has an embassy" or "has embassy"
    """
    # Strip out <ref>...</ref> tags as they contain spurious country name mentions
    # First remove self-closing ref tags like <ref name="abc" />
    notes_clean = re.sub(r'<ref[^>]*/>', '', notes, flags=re.IGNORECASE)
    # Then remove paired ref tags like <ref>...</ref>
    notes_clean = re.sub(r'<ref[^>]*>.*?</ref>', '', notes_clean, flags=re.DOTALL|re.IGNORECASE)
    
    # Remove wikilink markup [[...]] and [[...|...]] as it interferes with pattern matching
    # Replace [[link|text]] with just text
    notes_clean = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', notes_clean)
    # Replace [[link]] with just link
    notes_clean = re.sub(r'\[\[([^\]]+)\]\]', r'\1', notes_clean)
    
    # Normalize country names for comparison (handles "the X" vs "X")
    source_normalized = normalize_country_name(source_country).lower()
    target_normalized = normalize_country_name(target_country).lower()
    
    # Create list of alternative names/abbreviations for matching
    # This handles common abbreviations like "DR Congo", "DRC", "UK", "US", etc.
    def get_country_variants(country_name):
        """Get list of possible name variants for a country"""
        normalized = normalize_country_name(country_name).lower()
        variants = [normalized]
        
        # Common abbreviations and alternative names
        if 'democratic republic of the congo' in normalized or 'democratic republic of congo' in normalized:
            variants.extend(['dr congo', 'drc', 'congolese'])
        elif 'republic of the congo' in normalized or 'republic of congo' in normalized:
            variants.extend(['congo', 'republic of congo', 'congo-brazzaville', 'congolese'])
        elif 'united states' in normalized:
            variants.extend(['us', 'usa', 'u.s.', 'u.s.a.', 'american'])
        elif 'united kingdom' in normalized:
            variants.extend(['uk', 'u.k.', 'british'])
        elif 'united arab emirates' in normalized:
            variants.extend(['uae', 'u.a.e.', 'emirati'])
        elif 'central african republic' in normalized:
            variants.extend(['car', 'c.a.r.', 'c.a.r', 'central african'])
        elif 'gambia' in normalized:
            # Handle both "Gambia" and "the Gambia"
            variants.extend(['gambia', 'the gambia', 'gambian'])
        
        # Add adjective forms for common countries
        if 'russia' in normalized:
            variants.append('russian')
        elif 'china' in normalized:
            variants.append('chinese')
        elif 'japan' in normalized:
            variants.append('japanese')
        elif 'germany' in normalized:
            variants.append('german')
        elif 'france' in normalized:
            variants.append('french')
        elif 'spain' in normalized:
            variants.append('spanish')
        elif 'italy' in normalized:
            variants.append('italian')
        elif 'poland' in normalized:
            variants.append('polish')
        elif 'turkey' in normalized:
            variants.append('turkish')
        elif 'brazil' in normalized:
            variants.append('brazilian')
        elif 'india' in normalized:
            variants.append('indian')
        elif 'egypt' in normalized:
            variants.append('egyptian')
        elif 'nigeria' in normalized:
            variants.append('nigerian')
        elif 'saudi arabia' in normalized:
            variants.append('saudi')
        elif 'south africa' in normalized:
            variants.append('south african')
        elif 'mexico' in normalized:
            variants.append('mexican')
        elif 'canada' in normalized:
            variants.append('canadian')
        elif 'australia' in normalized:
            variants.append('australian')
        elif 'sweden' in normalized:
            variants.append('swedish')
        elif 'norway' in normalized:
            variants.append('norwegian')
        elif 'denmark' in normalized:
            variants.append('danish')
        elif 'netherlands' in normalized:
            variants.append('dutch')
        elif 'belgium' in normalized:
            variants.append('belgian')
        elif 'switzerland' in normalized:
            variants.append('swiss')
        elif 'austria' in normalized:
            variants.append('austrian')
        elif 'portugal' in normalized:
            variants.append('portuguese')
        elif 'greece' in normalized:
            variants.append('greek')
        elif 'iran' in normalized:
            variants.append('iranian')
        elif 'iraq' in normalized:
            variants.append('iraqi')
        elif 'israel' in normalized:
            variants.append('israeli')
        elif 'pakistan' in normalized:
            variants.append('pakistani')
        elif 'afghanistan' in normalized:
            variants.append('afghan')
        elif 'thailand' in normalized:
            variants.append('thai')
        elif 'vietnam' in normalized:
            variants.append('vietnamese')
        elif 'philippines' in normalized:
            variants.append('philippine')
        elif 'indonesia' in normalized:
            variants.append('indonesian')
        elif 'malaysia' in normalized:
            variants.append('malaysian')
        elif 'singapore' in normalized:
            variants.append('singaporean')
        elif 'korea' in normalized:
            if 'south' in normalized:
                variants.extend(['south korean', 'korean'])
            elif 'north' in normalized:
                variants.extend(['north korean', 'korean'])
        
        return variants
    
    source_variants = get_country_variants(source_country)
    target_variants = get_country_variants(target_country)
    
    # Split notes into bullet points (lines starting with *) OR by sentences (periods/semicolons)
    # First try splitting by bullet points
    lines = re.split(r'[\n\r]+\s*[\*•]', notes_clean)
    
    # If only one line (no bullet points), split by periods or semicolons to get sentences
    if len(lines) == 1:
        lines = re.split(r'[.;]\s*', notes_clean)
    
    # Filter out empty lines
    lines = [line.strip() for line in lines if line.strip()]
    
    source_has_embassy = False
    target_has_embassy = False
    
    for line in lines:
        line_lower = line.lower()
        
        # Special pattern: "Country A is accredited to Country B through its embassy in City"
        # This means Country A has an embassy in City (which is in Country B)
        accredited_match = re.search(r'(.+?)\s+is accredited to\s+(.+?)\s+through its (?:embassy|high commission) in', line_lower)
        if accredited_match:
            # The country before "is accredited" is the one with the embassy
            country_with_embassy = accredited_match.group(1).strip()
            
            # Check all variants
            if any(variant in country_with_embassy for variant in source_variants):
                source_has_embassy = True
            elif any(variant in country_with_embassy for variant in target_variants):
                target_has_embassy = True
            continue
        
        # Look for embassy/consulate/high commission phrases indicating a country HAS diplomatic presence
        # Patterns: "has an embassy", "maintains an embassy", "has a consulate", "has a high commission", etc.
        embassy_match = re.search(r'(has an? (?:embassy|consulate|high commission)|maintains an? (?:embassy|consulate|high commission)|(?:embassy|consulate|high commission) in)', line_lower)
        if not embassy_match:
            continue
        
        # The subject (country that HAS the embassy) should appear BEFORE the verb
        # Split at the embassy phrase to get the part before it
        before_embassy = line_lower[:embassy_match.start()]
        
        # For better accuracy, check which country appears CLOSEST to the embassy phrase
        # This handles cases like "Brunei has embassy in X, the Russian embassy in Y"
        # where both countries appear before the second "embassy in"
        
        source_positions = []
        target_positions = []
        
        for variant in source_variants:
            pos = before_embassy.rfind(variant)  # rfind = rightmost (closest to embassy phrase)
            if pos >= 0:
                source_positions.append(pos)
        
        for variant in target_variants:
            pos = before_embassy.rfind(variant)
            if pos >= 0:
                target_positions.append(pos)
        
        # The country whose name appears closest to the embassy phrase is the subject
        if source_positions and target_positions:
            # Both mentioned - use the one closest to the embassy phrase
            if max(source_positions) > max(target_positions):
                source_has_embassy = True
            else:
                target_has_embassy = True
        elif source_positions:
            source_has_embassy = True
        elif target_positions:
            target_has_embassy = True
    
    return source_has_embassy and target_has_embassy


def has_shared_membership(notes):
    """
    Check if the notes indicate both countries are members of same organization.
    Looks for phrases like:
    - "Both countries are full members of NATO"
    - "Both countries are members of the European Union"
    - "Both countries became members of the European Union"
    """
    # Strip out <ref>...</ref> tags as they may contain spurious text
    notes_clean = re.sub(r'<ref[^>]*/>', '', notes, flags=re.IGNORECASE)
    notes_clean = re.sub(r'<ref[^>]*>.*?</ref>', '', notes_clean, flags=re.DOTALL|re.IGNORECASE)
    
    notes_lower = notes_clean.lower()
    
    membership_patterns = [
        r'both countries are full members',
        r'both countries are members',
        r'both countries became members',
        r'both countries are member states',
        r'both.*are.*members? of',
        r'both.*became.*members? of',
        r'both nations are members',
        r'both countries belong',
        r'membership of both',
    ]
    
    for pattern in membership_patterns:
        if re.search(pattern, notes_lower):
            return True
    
    return False


# ---------- BUILD GRAPH ----------
G = nx.Graph()
G.add_nodes_from(countries)

# Create a mapping for normalized country names to actual node names
# This handles cases like "United States" (from flag) vs "the United States" (from filename)
country_mapping = {}
for country in countries:
    normalized = normalize_country_name(country).lower()
    country_mapping[normalized] = country
    # Also map the original name (in case it doesn't have "the")
    country_mapping[country.lower()] = country

# Track statistics
total_tables_found = 0
total_rows_processed = 0
edges_from_embassies = 0
edges_from_embassies_and_alliance = 0

print(f"\nBuilding graph (REQUIRE_ALLIANCE={REQUIRE_ALLIANCE})...")

for source_country, raw_text in tqdm(wiki_data.items(), desc="Processing countries"):
    # Find all potential bilateral relation tables
    tables = find_bilateral_tables(raw_text)
    total_tables_found += len(tables)
    
    if DEBUG and source_country == DEBUG_COUNTRY:
        print(f"\n\n{'='*80}")
        print(f"DEBUG: Processing {source_country}")
        print(f"Found {len(tables)} tables")
        print(f"{'='*80}")
    
    for table_idx, (table_text, _) in enumerate(tables):
        rows = parse_wikitable_rows(table_text)
        total_rows_processed += len(rows)
        
        if DEBUG and source_country == DEBUG_COUNTRY and table_idx < 2:
            print(f"\n--- Table {table_idx + 1} ---")
            print(f"Rows found: {len(rows)}")
            for i, row in enumerate(rows[:3]):  # Show first 3 rows
                print(f"\nRow {i+1}:")
                print(f"  Country: {row['country']}")
                print(f"  Notes (first 200 chars): {row['notes'][:200]}...")
        
        for row_idx, row in enumerate(rows):
            target_country_raw = row['country']
            notes = row['notes']
            
            # Map the target country name to the actual node name using normalization
            target_country_normalized = normalize_country_name(target_country_raw).lower()
            target_country = country_mapping.get(target_country_normalized)
            
            # Skip if target country not in our dataset or is the same as source
            if not target_country or target_country == source_country:
                continue
            
            # Check embassy condition (use raw name for comparison in notes)
            embassies_mutual = has_mutual_embassies(notes, source_country, target_country_raw)
            
            if DEBUG and DEBUG_DETAILED and source_country == DEBUG_COUNTRY and table_idx == 1 and row_idx < 5:
                print(f"\n  Checking {source_country} -> {target_country}:")
                print(f"    Mutual embassies: {embassies_mutual}")
                if not embassies_mutual:
                    print(f"    Notes preview: {notes[:300]}...")
            
            if not embassies_mutual:
                continue
            
            # Check alliance/membership condition
            has_alliance = has_shared_membership(notes)
            
            if DEBUG and DEBUG_DETAILED and source_country == DEBUG_COUNTRY and table_idx == 1 and row_idx < 5:
                print(f"    Has alliance: {has_alliance}")
            
            # Determine if we should add edge based on flag
            should_add_edge = False
            weight = 0.0
            
            if REQUIRE_ALLIANCE:
                # Only add edge if both embassies AND shared membership
                if embassies_mutual and has_alliance:
                    should_add_edge = True
                    weight = 1.0
                    edges_from_embassies_and_alliance += 1
            else:
                # Add edge if embassies exist
                if embassies_mutual:
                    should_add_edge = True
                    if has_alliance:
                        weight = 1.0
                        edges_from_embassies_and_alliance += 1
                    else:
                        weight = 0.5
                        edges_from_embassies += 1
            
            # Add or update edge
            if should_add_edge:
                if G.has_edge(source_country, target_country):
                    # Keep the maximum weight
                    G[source_country][target_country]["weight"] = max(
                        G[source_country][target_country]["weight"], 
                        weight
                    )
                else:
                    G.add_edge(source_country, target_country, weight=weight)

# ---------- STATISTICS ----------
# Count actual edges by weight
edges_by_weight = {}
for u, v, data in G.edges(data=True):
    weight = data.get('weight', 0.0)
    edges_by_weight[weight] = edges_by_weight.get(weight, 0) + 1

print(f"\n{'='*60}")
print(f"GRAPH STATISTICS")
print(f"{'='*60}")
print(f"Nodes (countries): {len(G.nodes())}")
print(f"Edges (relations): {len(G.edges())}")
print(f"Average edges per node: {len(G.edges())/len(G.nodes()):.1f}")
print(f"Total tables found: {total_tables_found}")
print(f"Total rows processed: {total_rows_processed}")
print(f"\nEDGE BREAKDOWN:")
if REQUIRE_ALLIANCE:
    print(f"  Edges with embassy + alliance: {len(G.edges())}")
else:
    print(f"  Edges with weight 0.5 (embassy only): {edges_by_weight.get(0.5, 0)}")
    print(f"  Edges with weight 1.0 (embassy + alliance): {edges_by_weight.get(1.0, 0)}")
    print(f"  Total edges: {len(G.edges())}")

# ---------- SAVE GRAPH ----------
output_filename = "foreign_relations_table_based"
if REQUIRE_ALLIANCE:
    output_filename += "_with_alliance.gexf"
else:
    output_filename += "_embassy_only.gexf"

nx.write_gexf(G, output_filename)
print(f"\n✓ Saved: {output_filename}")
print(f"{'='*60}")
