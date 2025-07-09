import json

from dotenv import load_dotenv

from export.models import Blocks, Documents, database

load_dotenv()


def update_action_table(chapter: int):
    old_data_path = (
        f"old_data/2025 TOWN PLAN DRAFT Chapter {chapter:02} v.07-15-2025.json"
    )
    with open(old_data_path) as f:
        chap_data = json.load(f)
        old_actions = chap_data["actions"]

    database.connect()

    try:
        document = Documents.get(collection_index=chapter)

        action_block = Blocks.get(document=document, type="action_table")

        for strat in action_block.content["strategies"]:
            print(strat["label"])
            old_strat = next(
                (s for s in old_actions["strategies"] if s["label"] == strat["label"]),
                None,
            )

            if not old_strat:
                continue

            for action in strat["actions"]:
                old_action = next(
                    (a for a in old_strat["actions"] if a["label"] == action["label"]),
                    None,
                )

                if not old_action:
                    continue

                if action["cost"] != old_action["cost"]:
                    action["cost"] = old_action["cost"]
                if action["responsibility"] != old_action["responsibility"]:
                    action["responsibility"] = old_action["responsibility"]

        action_block.save()

    finally:
        if not database.is_closed():
            database.close()
    pass


if __name__ == "__main__":
    for i in range(17):
        update_action_table(chapter=i + 1)
