import re

from models.card import DeckEntry


class DeckParseError(ValueError):
    def __init__(self, invalid_lines: list[tuple[int, str]]) -> None:
        self.invalid_lines = invalid_lines
        details = "; ".join(f"line {number}: {line}" for number, line in invalid_lines)
        super().__init__(f"Invalid decklist line(s): {details}")


class DeckParser:
    _quantity_line = re.compile(r"^(\d+)\s*x?\s+(.+?)\s*$", re.IGNORECASE)
    _set_collector_suffix = re.compile(r"\s+\([A-Z0-9]{2,6}\)\s+\d+[A-Z]?$", re.IGNORECASE)

    def parse(self, decklist: str) -> list[DeckEntry]:
        entries: list[DeckEntry] = []
        invalid_lines: list[tuple[int, str]] = []

        for line_number, raw_line in enumerate(decklist.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue

            match = self._quantity_line.fullmatch(line)
            if match:
                quantity = int(match.group(1))
                name = match.group(2).strip()
                if quantity < 1 or not name:
                    invalid_lines.append((line_number, raw_line))
                    continue
            elif line[0].isdigit():
                invalid_lines.append((line_number, raw_line))
                continue
            else:
                quantity, name = 1, line

            name = self._set_collector_suffix.sub("", name).strip()
            if not name:
                invalid_lines.append((line_number, raw_line))
                continue
            entries.append(DeckEntry(quantity=quantity, name=name))

        if invalid_lines:
            raise DeckParseError(invalid_lines)
        if not entries:
            raise DeckParseError([(1, "(empty decklist)")])
        return entries

    def parse_names(self, lines: str) -> list[str]:
        if not lines.strip():
            return []
        return list(dict.fromkeys(entry.name for entry in self.parse(lines)))