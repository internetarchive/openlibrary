"""New form library to use instead of web.form.

(this should go to web.py)
"""
import web
import copy
import re

from infogami.utils.view import render

class AttributeList(dict):
    """List of atributes of input.
    
    >>> a = AttributeList(type='text', name='x', value=20)
    >>> a
    <attrs: 'type="text" name="x" value="20"'>x
    """
    def copy(self):
        return AttributeList(self)
        
    def __str__(self):
        return " ".join('%s="%s"' % (k, web.websafe(v)) for k, v in self.items())
        
    def __repr__(self):
        return '<attrs: %s>' % repr(str(self))

class Input:
    def __init__(self, name, description=None, value=None, **kw):
        self.name = name
        self.description = description or ""
        self.value = value
        self.validators = kw.pop('validators', [])
        
        self.help = kw.pop('help', None)
        self.note = kw.pop('note', None)
        
        self.id = kw.pop('id', name)
        self.__dict__.update(kw)
        
        if 'klass' in kw:
            kw['class'] = kw.pop('klass')
        
        self.attrs = AttributeList(kw)
        
    def get_type(self):
        raise NotImplementedError
        
    def is_hidden(self):
        return False
        
    def render(self):
        attrs = self.attrs.copy()
        attrs['id'] = self.id
        attrs['type'] = self.get_type()
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
    
    >>> t = Textbox("name", description='Name', value='joe')
    >>> t.render()
    '<input type="text" id="name" value="joe" name="name" />'

    >>> t = Textbox("name", description='Name', value='joe', id='name', klass='input', size=10)
    >>> t.render()
    '<input name="name" value="joe" class="input" type="text" id="name" size="10" />'
    """
    def get_type(self):
        return "text"

class Password(Input):
    """Password input.
    
        >>> Password("password", description='Password', value='secret').render()
        '<input type="password" id="password" value="secret" name="password" />'
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
    def is_hidden(self):
        return True

    def get_type(self):
        return "hidden"

class Form:
    def __init__(self, *inputs, **kw):
        self.inputs = inputs
        self.validators = kw.pop('validators', [])
        self.note = None
        
    def __call__(self):
        return copy.deepcopy(self)
        
    def __str__(self):
        return web.safestr(self.render())
        
    def __getitem__(self, key):
        for i in self.inputs:
            if i.name == key:
                return i
        raise KeyError, key
        
    def __getattr__(self, name):
        # don't interfere with deepcopy
        inputs = self.__dict__.get('inputs') or []
        for x in inputs:
            if x.name == name: return x
        raise AttributeError, name

    def render(self):
        return render.form(self)
        
    def validates(self, source):
        valid = True
        
        for i in self.inputs:
            v = source.get(i.name)
            valid = i.validate(v) and valid

        valid = self._validate(source) and valid
        self.valid = valid
        return valid
        
    fill = validates
        
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
            raise
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
