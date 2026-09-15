from data_foundry.quality.normalize import (
    clean_text,
    fix_encoding,
    normalize_lang,
    null_if_sentinel,
    parse_int_locale,
    parse_year,
)


def test_fix_encoding_repairs_mojibake():
    assert fix_encoding("SÃ£o Paulo") == "São Paulo"


def test_fix_encoding_is_idempotent():
    fixed = fix_encoding("SÃ£o Paulo")
    assert fix_encoding(fixed) == fixed


def test_clean_text_collapses_whitespace_and_nbsp():
    assert clean_text("  a\xa0 b ") == "a b"


def test_clean_text_none_and_blank():
    assert clean_text(None) is None
    assert clean_text("   \xa0  ") is None


def test_null_if_sentinel():
    assert null_if_sentinel("N/A") is None
    assert null_if_sentinel("--") is None
    assert null_if_sentinel("Sem Informação") is None
    assert null_if_sentinel(None) is None
    assert null_if_sentinel("Machado de Assis") == "Machado de Assis"


def test_parse_int_locale():
    assert parse_int_locale("1.234") == 1234
    assert parse_int_locale("1,234") == 1234
    assert parse_int_locale("1 234") == 1234
    assert parse_int_locale("12.345 acessos") == 12345
    assert parse_int_locale("abc") is None
    assert parse_int_locale(None) is None


def test_parse_year():
    assert parse_year("2005") == 2005
    assert parse_year("Ano: 2005") == 2005
    assert parse_year("2005.") == 2005
    assert parse_year("9999") is None
    assert parse_year(None) is None


def test_normalize_lang_maps_known_variants():
    assert normalize_lang("Português") == "pt"
    assert normalize_lang("portugues") == "pt"
    assert normalize_lang("pt-BR") == "pt"
    assert normalize_lang("English") == "en"
    assert normalize_lang("Inglês") == "en"


def test_normalize_lang_keeps_unknown_values():
    assert normalize_lang("Klingon") == "Klingon"
    assert normalize_lang(None) is None
