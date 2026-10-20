"""Byte-based operation accounting; no timer-based percentages."""
class ByteProgress:
    def __init__(self):
        self.steps = {}

    def plan(self, steps):
        for name, size in steps.items():
            self.steps[name] = [min(self.steps.get(name, [0, 0])[0], int(size)), int(size)]

    def advance(self, name, done, total):
        total = max(0, int(total))
        self.steps[name] = [min(max(0, int(done)), total), total]

    def fields(self, complete=False):
        done = sum(x[0] for x in self.steps.values())
        total = sum(x[1] for x in self.steps.values())
        return dict(processed_bytes=done, total_bytes=total,
                    percent=100 if complete else min(99, int(done*100/total)) if total else 0)
