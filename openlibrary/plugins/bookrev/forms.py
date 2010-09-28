from web.form import Form, Hidden, Textarea, Textbox, Validator

required = Validator("Required", lambda x: x and x.strip())

review_form = Form(
    Hidden('edition', required),
    Textbox('title'),
    Textarea('text', required)
)
