import enum


class ResultsInfoSection(enum.Enum):
    GENERAL = "1. General"
    RESULTS = "2. Results"


info = {}


def add_info(name: str, value="", section=ResultsInfoSection.RESULTS):
    if section not in info:
        info[section] = []

    info[section].append(str(name) + ": " + str(value))


def save_info(filepath):
    with open(filepath, "w") as f:
        for section, rows in sorted(info.items(), key=lambda x: x[0].value):
            f.write(f"##########\n" f"{section.value}\n" f"##########\n\n")
            f.write("\n".join(rows) + "\n\n")
