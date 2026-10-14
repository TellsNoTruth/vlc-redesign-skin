"""A minimal XML element builder: enough for theme.xml, nothing more."""
from xml.sax.saxutils import quoteattr


class E:
    """An element with ordered attributes. Attributes whose value is None are dropped,
    so callers can pass optional ones unconditionally."""

    def __init__(self, tag, **attrs):
        self.tag = tag
        self.attrs = {k: v for k, v in attrs.items() if v is not None}
        self.children = []

    def add(self, *children):
        self.children.extend(children)
        return self

    def render(self, depth=0):
        pad = "  " * depth
        attrs = "".join(f" {k}={quoteattr(_str(v))}" for k, v in self.attrs.items())
        if not self.children:
            return f"{pad}<{self.tag}{attrs}/>\n"
        inner = "".join(
            c.render(depth + 1) if isinstance(c, E) else f"{pad}  <!-- {c} -->\n"
            for c in self.children
        )
        return f"{pad}<{self.tag}{attrs}>\n{inner}{pad}</{self.tag}>\n"


def _str(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
