from extrusion_monitor.recipes import Limit, Recipe, RecipeStore, recipe_from_csv, recipe_to_csv


def test_store_roundtrip(tmp_path):
    store = RecipeStore(tmp_path)
    r = Recipe(name="THHN 12/AWG", limits={"z1": Limit(nominal=160, warn=2, alarm=5)})
    store.save(r)
    again = RecipeStore(tmp_path)
    assert again.get("THHN 12/AWG").limits["z1"].nominal == 160
    assert again.find_by_display_name("thhn-12 awg").name == "THHN 12/AWG"
    again.delete("THHN 12/AWG")
    assert RecipeStore(tmp_path).names() == []


def test_csv_roundtrip_and_semicolon():
    r = Recipe(name="X", limits={"z1": Limit(nominal=160.5, warn=2, alarm=5, mode="pct")})
    back = recipe_from_csv("X", recipe_to_csv(r))
    assert back.limits["z1"] == r.limits["z1"]
    excel = "variable;nominal;warn;alarm;mode;reference\nz2;170,5;1;3;abs;recipe\n"
    assert recipe_from_csv("Y", excel).limits["z2"].nominal == 170.5
