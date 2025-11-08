from hexscribe import HexScreenRenderer
from settings import WIDTH, HEIGHT

HEX_ID = "1106"
DESCRIPTION = ("Bribed taxman; undead pirates run the docks. "
               "Templar orphanage seeks proof of a pact. "
               "Cold bells at dusk; fog rolls in from the bay.")
FEATURES = [
    ("undead", "Undead activity"),
    ("smuggling", "Smuggling ring"),
    ("cross", "Templar orphanage"),
    ("keep", "Old river keep"),
]

if __name__ == "__main__":
    rnd = HexScreenRenderer(WIDTH, HEIGHT, split_x=380, cells_across=6)
    img = rnd.render(HEX_ID, DESCRIPTION, FEATURES, marks=None)  # marks=None -> random diamonds
    img.save("hex_demo.png")
    print("Wrote hex_demo.png")
