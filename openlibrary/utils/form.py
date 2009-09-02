"""New form library to use instead of web.form.

(this should go to web.py)
"""
import web
import copy
import re

class AttributeList(dict):
    """List of atributes of input.
    
    >>> a = AttributeList(type='text', name='x', value=20)
    >>> a
    <attrs: 'type="text" name="x" value="20"'>
    """
    def copy(self):
        return AttributeList(self)
        
    def __str__(self):
        return " ".join('%s="%s"' % (k, web.websafe(v)) for k, v in self.items())
        
    def __repr__(self):
        return '<attrs: %s>' % repr(str(self))

class Input:
    def __init__(self, name, label, value=None, **kw):
        self.name = name
        self.label = label
        self.value = value
        self.validators = kw.pop('validators', [])
        
        self.description = kw.pop('description', None)
        self.note = kw.pop('note', None)
        
        self.id = None
        self.__dict__.update(kw)
        
        if 'klass' in kw:
            kw['class'] = kw.pop('klass')
        
        self.attrs = AttributeList(kw)
        
    def get_type(self):
        raise NotImplementedError
        
    def render(self):
        attrs = self.attrs.copy()
        
        attrs['type'] = 'text'
        attrs['name'] = self.name
        attrs['value'] = self.value or ''
            
        return '<input ' + str(attrs) + ' />'

    def validate(self, value):
        self.value = value
        for v in self.validators:
            if not v.valid(value):
                self.note = v.msg
                return False
        return True        
        
class Textbox(Input):
    """Textbox input.
    
    >>> t = Textbox("name", label='Name', value='joe')
    >>> t.render()
    '<input type="text" name="name" value="joe" />'

    >>> t = Textbox("name", label='Name', value='joe', id='name', klass='input', size=10)
    >>> t.render()
    '<input name="name" value="joe" id="name" type="text" class="input" size="10" />'
    """
    def get_type(self):
        return "text"

class Password(Input):
    """Password input.
    
        >>> Password("password", label='Password', value='secret').render()
        <input type="password" value="secret" />
    """
    def get_type(self):
        return "password"
        
class Checkbox(Input):
    """Checkbox input."""
    
    def get_type(self):
        return "checkbox"
        
class Hidden(Input):
    """Hidden input.
    """
    def get_type(self):
        return "hidden"

class Form:
    def __init__(self, *inputs, **kw):
        self.inputs = inputs
        self.validators = kw.pop('validators', [])
        
    def __call__(self):
        return copy.deepcopy(self)

    def render(self):
        return "\n".join(self._render())
        
    def _render(self):
        for i in self.inputs:
            id = i.id or i.name
            
            if i.hidden:
                yield i.render()
            else:
                yield '<div class="formElement">'
                yield '  <div class="label"><label for="%s">%s</label> <span class="smaller lighter">%s</span></div>' % (web.websafe(id), web.websafe(i.label), web.websafe(i.description))
                yield '  <div class="input">'
                yield '    ' + i.render()
                yield '    <div class="invalid" htmlfor="%s">%s</div>' % (web.websafe(id), web.websafe(i.note))
                yield '  </div>'
                yield '</div>'
            
    def validates(self, source):
        valid = True
        
        for i in self.inputs:
            v = source.get(i.name)
            valid = i.validate(v) and valid

        valid = self._validate(source) and valid
        self.valid = valid
        return valid
        
    def _validate(self, value):
        for v in self.validators:
            if not v.valid(value):
                self.note = v.msg
                return False
        return True

class Validator:
    def __init__(self, msg, test): 
        self.msg = msg
        self.test = test
        
    def __deepcopy__(self, memo): 
        return copy.copy(self)

    def valid(self, value): 
        try: 
            return self.test(value)
        except: 
            return False
            
    def __repr__(self):
        return "<validator: %r >" % self.msg

notnull = Validator("Required", bool)

class RegexpValidator(Validator):
    def __init__(self, rexp, msg):
        self.rexp = re.compile(rexp)
        self.msg = msg
    
    def valid(self, value):
        return bool(self.rexp.match(value))

if __name__ == "__main__":
    import doctest
    doctest.testmod()
