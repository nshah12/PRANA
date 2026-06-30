"""
Restore AIOKafkaConsumer to __init__ for broken consumer files.
Fixes syntax errors introduced by previous script attempts.
"""
import re
from pathlib import Path

CONSUMERS_DIR = Path(__file__).parent.parent / "kafka" / "consumers"

PLACEHOLDER = "self._consumer = None  # created in run()"

for f in sorted(CONSUMERS_DIR.glob("*.py")):
    if f.name == "__init__.py":
        continue
    src = f.read_text(encoding="utf-8")

    if PLACEHOLDER not in src:
        print(f"SKIP (no placeholder): {f.name}")
        continue

    # The broken run() body starts with self._consumer = AIOKafkaConsumer(
    # and ends with a broken `await self._consumer.start())` + duplicate await line.
    # We need to:
    # 1. Extract the AIOKafkaConsumer(...) args
    # 2. Put them back in __init__ as a proper AIOKafkaConsumer call
    # 3. Clean up run() to have just: await self._consumer.start()

    # Pattern: self._consumer = AIOKafkaConsumer(
    #   ... (indented args) ...
    #   value_deserializer=lambda b: json.loads(b),
    #   await self._consumer.start())  ← broken line
    #   await self._consumer.start()   ← duplicate

    # Find the broken block in run()
    broken_block_pat = re.compile(
        r'([ \t]*)(self\._consumer = AIOKafkaConsumer\(.*?value_deserializer=[^\n]+),?\n'
        r'[ \t]*await self\._consumer\.start\(\)\)\n'
        r'[ \t]*await self\._consumer\.start\(\)',
        re.DOTALL,
    )

    m = broken_block_pat.search(src)
    if not m:
        print(f"SKIP (broken block not found): {f.name}")
        continue

    run_indent = m.group(1)        # e.g. "        "
    aiokafka_block = m.group(2)    # e.g. "self._consumer = AIOKafkaConsumer(\n    ..."

    # Normalise indentation of the aiokafka block to match __init__ body (8 spaces)
    # Strip leading indent from each line, then re-indent to 8 spaces
    block_lines = aiokafka_block.splitlines()
    # Find the minimum indent (first line has run_indent already stripped from group match)
    reindented_lines = []
    for i, line in enumerate(block_lines):
        if i == 0:
            reindented_lines.append("        " + line.lstrip())
        else:
            reindented_lines.append("        " + line.lstrip())
    # Add closing paren on its own line (8-space indent)
    reindented_lines.append("        )")
    proper_block = "\n".join(reindented_lines)

    # Replace placeholder in __init__ with the proper block
    new_src = src.replace(
        "        " + PLACEHOLDER,
        proper_block,
    )

    # Remove the broken block from run() and leave just await self._consumer.start()
    new_src = broken_block_pat.sub(
        run_indent + "await self._consumer.start()",
        new_src,
    )

    f.write_text(new_src, encoding="utf-8")
    print(f"FIXED: {f.name}")

print("Done.")
