class RoleEffectsMixin:

    def is_affected(self, pid):
        return self.is_poisoned(pid) or self.is_drunk(pid)

    def is_poisoned(self, pid):
        return self.state[pid].get("poisoned", False)

    def is_drunk(self, pid):
        return self.state[pid].get("drunk", False)
