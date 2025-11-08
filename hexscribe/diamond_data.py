# hexscribe/diamond_data.py
from typing import Dict

# Each value maps to a single feature dict with name/type/text.
DIAMOND_FEATURE: Dict[int, dict] = {
    1: {
        "name": "The Field of Bones",
        "type": "Place of Power",
        "text": (
            "A scholar academy covets the bones, but slinker hounds menace any scavenger bold enough "
            "to gather them. The bones are piled here by an order of scholars returning from expeditions "
            "across this region and beyond. Weird resonances attract a ghost singer who hums through the site."
        ),
        "category": "Into the Wilderness",
    },
    2: {
        "name": "The Missing Gate",
        "type": "Portal",
        "text": (
            "Insecure warlords rely on it; conservative wizards despise it. It is 'missing' because the other "
            "gates were found and razed. The worst of its history: it once sparked a cataclysmic civil war "
            "in this area."
        ),
        "category": "Stranger Places",
    },
    3: {
        "name": "The Spring Estate",
        "type": "Outpost",
        "text": (
            "Nearby woods brim with rare herbs, but a walled-up dream-walker haunts the grounds. A miller once "
            "fortified his mill here, and now a retired assassin quietly runs a body-disposal service."
        ),
        "category": "Settled Lands",
    },
    4: {
        "name": "Shrine of Chains",
        "type": "Place of Power",
        "text": (
            "Undead guardians keep vigil while a royal bloodline vows to crush the site. Built for grim rites: "
            "the heads of scholars are sacrificed to bind their knowledge to the shrine. Pilgrims arrive seeking "
            "the will of an otherworldly patron."
        ),
        "category": "The Underrealms",
    },
    5: {
        "name": "Upriver Ruin",
        "type": "Hazard",
        "text": (
            "Primary danger: lethal wasps. Secondary threat: a mean drunk wizard. The site remains unclaimed due "
            "to disputes over who rules these waters. Those who come may yet rescue stranded locals."
        ),
        "category": "On the High Seas",
    },
}

def feature_for(value: int) -> dict:
    return DIAMOND_FEATURE.get(int(value), {
        "name": "(no feature)",
        "type": "",
        "text": "Select a numbered diamond (1–5) to view its details.",
        "category": "",
    })
