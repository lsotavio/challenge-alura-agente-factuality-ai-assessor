from src.highlights import highlighted_fragments, scoped_target


def test_discontinuous_highlights_do_not_absorb_neighboring_table_cells() -> None:
    response = "20/06/2026 | Equipe Dourada | Arena Central (Torneio - Grupo L)"
    target = "20/06/2026\nEquipe Dourada"

    assert highlighted_fragments(response, target) == ["20/06/2026", "Equipe Dourada"]
    assert scoped_target(response, target) == "20/06/2026 | Equipe Dourada"
    assert "Toronto" not in scoped_target(response, target)
    assert "Grupo L" not in scoped_target(response, target)


def test_contiguous_highlight_remains_one_fragment() -> None:
    target = "Telefone: (22) 2645-3600"
    assert highlighted_fragments(f"Contato\n{target}", target) == [target]
