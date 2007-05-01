from web.form import *

template_preferences = Form(
    Textbox("path", description="Template Root"),
    Button("Save")
)

if __name__ == "__main__":
    print template_preferences().render()