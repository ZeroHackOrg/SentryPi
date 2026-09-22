_CONTROL_OPS = {"BRANCH", "DELAY", "LOOP", "WHILE", "TIMER", "JUMP", "ANALOG_READ"}


def optimize(tac):
    removed = 0
    optimized = []
    allocated = set()
    aliased = set()
    previous_write = None

    for instruction in tac:
        op = instruction["op"]
        if op == "ALLOC_PIN":
            key = (instruction["reg"], instruction["pin"], instruction["mode"])
            if key in allocated:
                removed += 1
                continue
            allocated.add(key)
        elif op == "MAP_ALIAS":
            key = (instruction["reg"], instruction["alias"])
            if key in aliased:
                removed += 1
                continue
            aliased.add(key)
        elif op == "WRITE_BIT":
            key = (instruction["reg"], instruction["value"])
            if key == previous_write:
                removed += 1
                continue
            previous_write = key
        elif op in _CONTROL_OPS:
            previous_write = None
        optimized.append(instruction)

    return optimized, removed