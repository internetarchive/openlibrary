def map(doc):
    ctx = doc.get("context")
    if isinstance(ctx, dict):
        for i in ctx.get("keys",[]):
            yield [i,doc.get("started_at","")], None
