from fly_competency_atlas.registry import catalog
from fly_competency_atlas.upstream import parse_datasets, parse_tutorials


def test_catalog_contains_expected_first_panel() -> None:
    slugs = {entry.slug for entry in catalog()}
    assert "lamina_cartridge" in slugs
    assert "osn_ephys" in slugs
    assert "optic_lobe_1_0" in slugs
    assert "hemibrain_1_2" in slugs
    assert "flywire_783" in slugs


def test_parse_tutorials_extracts_levels_and_links() -> None:
    markdown = """
### Introductory
* [Intro](https://example.com/intro)
### Advanced
* [Cartridge](https://example.com/cartridge)
"""
    records = parse_tutorials(markdown)
    assert [record.level for record in records] == ["Introductory", "Advanced"]
    assert records[1].name == "Cartridge"
    assert records[1].url == "https://example.com/cartridge"


def test_parse_datasets_extracts_versions_and_links() -> None:
    markdown = (
        '## <a name="hemibrain"></a>[Hemibrain Dataset](https://example.com/source)\n'
        "|Hemibrain Ver.| NeuroArch Ver.| Download Link |Loading Script|Last Update|NeuroNLP|\n"
        "|-----------|---------| --------| -------|------|-------|\n"
        "| [1.2](https://example.com/v1.2) | abc123 | "
        "[backup.zip](https://example.com/backup.zip) | "
        "[Link](https://example.com/load.ipynb) | 06/17/2022 | "
        "[Link](https://example.com/nlp) |\n"
    )
    records = parse_datasets(markdown)
    assert len(records) == 1
    assert records[0].dataset == "Hemibrain Dataset"
    assert records[0].version == "1.2"
    assert records[0].last_update == "06/17/2022"
    assert records[0].loading_script_url == "https://example.com/load.ipynb"
    assert records[0].neuronlp_url == "https://example.com/nlp"
