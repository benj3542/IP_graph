# Table-Based Foreign Relations Graph Creator

## Overview

This script (`create_graph_from_tables.py`) creates a network graph from Wikipedia "Foreign Relations" articles by parsing wikitables that contain bilateral relations information.

## How It Works

### Data Source
- **Input**: JSON files in `wiki_foreign_relations_jsons/` folder
- Each JSON file contains the raw wikitext from a Wikipedia "Foreign relations of [Country]" page
- Example: `Foreign relations of Denmark.json`

### Edge Creation Logic

An edge is created between two countries based on two conditions:

#### 1. Embassy Condition (Required)
Both countries must have embassies in each other's countries. This is detected by looking for bullet points in the wikitable notes like:
```
* Denmark has an embassy in Berlin
* Germany has an embassy in Copenhagen
```

#### 2. Alliance/Membership Condition (Optional)
Both countries are members of the same international organization. Detected by phrases like:
```
* Both countries are full members of the European Union
* Both countries are members of NATO
```

### Configuration Flag

The `REQUIRE_ALLIANCE` flag controls which edges are created:

- **`REQUIRE_ALLIANCE = True`**: 
  - Only create edges where BOTH conditions are met
  - All edges have weight = 1.0
  - More restrictive, fewer edges

- **`REQUIRE_ALLIANCE = False`**: 
  - Create edges if embassy condition is met
  - Edge weight = 0.5 if only embassies exist
  - Edge weight = 1.0 if both embassies AND alliance exist
  - More permissive, more edges

## Usage

### Basic Usage

1. Make sure your JSON files are in the `wiki_foreign_relations_jsons/` folder

2. Edit the script to set your preferred configuration:
```python
REQUIRE_ALLIANCE = False  # or True
```

3. Run the script:
```bash
/Users/smilladue/Desktop/Documents/DTU/social-graphs/.venv/bin/python create_graph_from_tables.py
```

### Output Files

The script creates a GEXF file based on the configuration:
- `foreign_relations_table_based_embassy_only.gexf` - when `REQUIRE_ALLIANCE = False`
- `foreign_relations_table_based_with_alliance.gexf` - when `REQUIRE_ALLIANCE = True`

### Debug Mode

To see detailed output for a specific country:
```python
DEBUG = True
DEBUG_COUNTRY = "Denmark"  # Change to country of interest
```

## Example Results

### With Alliance Requirement (`REQUIRE_ALLIANCE = True`)
```
Nodes (countries): 195
Edges (relations): 133
Edges (embassy + alliance): 146
```

### Without Alliance Requirement (`REQUIRE_ALLIANCE = False`)
```
Nodes (countries): 195
Edges (relations): 387
  Edges (embassy only): 278
  Edges (embassy + alliance): 146
  Total: 424
```

## Key Features

### Robust Table Parsing
- Handles nested wikitable syntax (`{| ... |}`)
- Parses complex table structures with varying column formats
- Extracts country names from `{{flag|CountryName}}` templates

### Flexible Matching
- Case-insensitive pattern matching
- Multiple embassy phrase patterns (e.g., "has an embassy", "maintains an embassy")
- Multiple alliance phrase patterns

### Statistics Tracking
- Reports total tables found
- Reports total rows processed
- Breaks down edges by type

## Comparison with Original Script

### Original `create_graph_list.py`
- **Approach**: Sentence-based parsing looking for sequential patterns
- **Logic**: Looks for sentences mentioning embassies followed by alliance mentions
- **Granularity**: Word-level parsing with complex cleanup
- **Output**: `foreign_relations_graph_simple_embassy_org.gexf`

### New `create_graph_from_tables.py`
- **Approach**: Table-based parsing of structured wikitables
- **Logic**: Parses bilateral relations tables with country-notes structure
- **Granularity**: Structured data extraction from tables
- **Output**: `foreign_relations_table_based_[variant].gexf`
- **Advantage**: More accurate as tables are already structured

## Troubleshooting

### No edges created?
- Check if `DEBUG = True` and examine the parsed tables
- Verify the JSON files contain wikitables with `class="wikitable"`
- Ensure the tables have the expected structure (Country, Date, Notes columns)

### Too few edges?
- Try setting `REQUIRE_ALLIANCE = False` to include embassy-only relations
- Check if the embassy and alliance detection patterns match your data

### Too many edges?
- Set `REQUIRE_ALLIANCE = True` to require both conditions
- The script may be too permissive in detecting embassies

## Dependencies

- Python 3.7+
- `networkx` - for graph creation
- `tqdm` - for progress bars
- Standard library: `os`, `json`, `re`

## Future Improvements

Potential enhancements:
1. More sophisticated embassy detection (handle consulates, etc.)
2. Different weight schemes based on relationship strength
3. Additional conditions (trade agreements, treaties, etc.)
4. Handle edge cases in country name matching
5. Support for historical relationship changes
