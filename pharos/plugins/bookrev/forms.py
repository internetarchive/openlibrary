from web.form import Form, Hidden, Textarea, Validator

required = Validator("Required", lambda x: x and x.strip())

review_form = Form(
    Hidden('edition', required),
    Textarea('text', required)
)
