"""utility to generate db schema for any database engine.
(should go to web.py)
"""

__all__ = [
    "Schema", "Table", "Column",
    "register_datatype", "register_constant",
]

_datatypes = {}
def register_datatype(name, datatype):
    _datatypes[name] = datatype

_adapters = {}
def register_adapter(name, adapter):
    _adapters[name] = adapter
    
def get_adapter(name):
    if isinstance(name, AbstractAdapter):
        return name
    else:
        return _adapters[name]()

_constants = {}
def register_constant(name, constant):
    _constants[name] = constant
    
def get_constant(name):
    return _constants(name)

class AbstractAdapter:
    def type_to_sql(self, type, limit=None):
        sql = self.get_native_type(type)
        if limit:
            sql += '(%s)' % limit
        return sql
        
    def get_native_type(self, type):
        return self.native_types[type]
        
    def index_name(self, table, columns):
        return "_".join([table] + columns + ["idx"])
        
    def references_to_sql(self, column_name, value):
        # foreign key constraints are not supported by default
        return None
        
    def column_option_to_sql(self, column, option, value):
        if option == 'primary_key' and value is True:
            return 'primary key'
        elif option == 'unique' and value is True:
            return 'unique'
        elif option == 'default':
            if hasattr(value, 'sql'):
                value = value.sql(self)
            else:
                value = sqlrepr(value)
            return "default %s" % (value)
        elif option == 'null':
            return {True: 'null', False: 'not null'}[value]
        elif option == 'references':
            return self.references_to_sql(column, value)
    
    def get_constant(self, name):
        return self.constants[name]
        
    def quote(self):
        raise NotImplementedError()
        
class MockAdapter(AbstractAdapter):
    def get_native_type(self, type):
        return type
        
    def references_to_sql(self, column_name, value):
        return 'references ' + value
        
    def quote(self, value):
        return repr(value)

class MySQLAdapter(AbstractAdapter):
    native_types = {
        'serial': 'int auto_increment not null',
        'integer': 'int',
        'float': 'float',
        'string': 'varchar',
        'text': 'text',
        'datetime': 'datetime',
        'timestamp': 'datetime',
        'time': 'time',
        'date': 'date',
        'binary': 'blob',
        'boolean': 'boolean'
    }
    constants = {
        'CURRENT_TIMESTAMP': 'CURRENT_TIMESTAMP',
        'CURRENT_DATE': 'CURRENT_DATE',
        'CURRENT_TIME': 'CURRENT_TIME',
        'CURRENT_UTC_TIMESTAMP': 'UTC_TIMESTAMP',
        'CURRENT_UTC_DATE': 'UTC_DATE',
        'CURRENT_UTC_TIME': 'UTC_TIME',
    }
    def references_to_sql(self, column_name, value):
        return {'constraint': 'foreign key (%s) references %s' % (column_name, value)}

class PostgresAdapter(AbstractAdapter):  
    native_types = {
        'serial': 'serial',
        'integer': 'int',
        'float': 'float',
        'string': 'character varying',
        'text': 'text',
        'datetime': 'timestamp',
        'timestamp': 'timestamp',
        'time': 'time',
        'date': 'date',
        'binary': 'bytea',
        'boolean': 'boolean'
    }
    constants = {
        'CURRENT_TIMESTAMP': 'current_timestamp',
        'CURRENT_DATE': 'current_date',
        'CURRENT_TIME': 'current_time',
        'CURRENT_UTC_TIMESTAMP': "(current_timestamp at time zone 'utc')",
        'CURRENT_UTC_DATE': "(date (current_timestamp at timezone 'utc'))",
        'CURRENT_UTC_TIME': "(current_time at time zone 'utc')",
    }
    
    def references_to_sql(self, column_name, value):
        return 'references ' + value
    
class SQLiteAdapter(AbstractAdapter):
    native_types = {
        'serial': 'integer autoincrement',
        'integer': 'integer',
        'float': 'float',
        'string': 'varchar',
        'text': 'text',
        'datetime': 'datetime',
        'timestamp': 'datetime',
        'time': 'datetime',
        'date': 'date',
        'binary': 'blob',
        'boolean': 'boolean'
    }
    constants = {
        'CURRENT_TIMESTAMP': "CURRENT_TIMESTAMP",
        'CURRENT_DATE': "CURRENT_DATE",
        'CURRENT_TIME': "CURRENT_TIME",
        'CURRENT_UTC_TIMESTAMP': "CURRENT_TIMESTAMP",
        'CURRENT_UTC_DATE': "CURRENT_DATE",
        'CURRENT_UTC_TIME': "CURRENT_TIME",
    }

register_adapter('mysql', MySQLAdapter)
register_adapter('postgres', PostgresAdapter)
register_adapter('sqlite', SQLiteAdapter)

def sqlrepr(s):
    if isinstance(s, str):
        return repr(s)
    else:
        return s

class Datatype:
    def __init__(self, name=None):
        self.name = name
        
    def sql(self, engine):
        return get_adapter(engine).type_to_sql(self.name)
        
class Constant:
    def __init__(self, name=None):
        self.name = name
        
    def sql(self, engine):
        return get_adapter(engine).get_constant(self.name)
        
for c in ['CURRENT_TIMESTAMP', 'CURRENT_DATE', 'CURRENT_TIME', 'CURRENT_UTC_TIMESTAMP', 'CURRENT_UTC_DATE', 'CURRENT_UTC_TIME']:
    register_constant(c, Constant(c))

class Schema:
    def __init__(self):
        self.tables = [] 
        self.indexes = []
        
        for name, value in _constants.items():
            setattr(self, name, value)
    
    def column(self, name, type, **options):
        return Column(name, type, **options)
        
    def add_table(self, name, *columns, **options):
        t = Table(name, *columns, **options)
        self.tables.append(t)
        
    def add_index(self, table, columns, **options):
        i = Index(table, columns, **options)
        self.indexes.append(i)
        
    def sql(self, engine):
        return "\n".join(x.sql(engine) for x in self.tables + self.indexes)

class Table:
    """Database table.
        >>> t = Table('user', Column('name', 'string'))
        >>> print t.sql('postgres')
        create table user (
            name character varying(255)
        );
    """
    def __init__(self, name, *columns, **options):
        self.name = name
        self.columns = columns
        self.options = options

    def sql(self, engine):
        columns = [c.sql(engine) for c in self.columns]
        for c in self.columns:
            for constraint in c.constraints:
                columns.append(constraint)
        return "create table %s (\n    %s\n);" % (self.name, ",\n    ".join(columns))

class Column:
    """Column in a database table.
        
        >>> Column('name', 'text').sql('mock')
        'name text'
        >>> Column('id', 'serial', primary_key=True).sql('mock')
        'id serial primary key'
        >>> Column('revision', 'integer', default=1).sql('mock')
        'revision integer default 1'
        >>> Column('name', 'string', default='joe').sql('mock')
        "name string(255) default 'joe'"
    """
    def __init__(self, name, type, **options):
        self.name = name
        self.type = type
        self.options = options
        self.limit = self.options.pop('limit', None)
        self.constraints = []
        
        self.primary_key = self.options.get('primary_key')
        self.unique = self.options.get('unique')
        self.references = self.options.get('references')
        
        # string type is of variable length. set default length as 255.
        if type == 'string':
            self.limit = self.limit or 255
            
    def sql(self, engine):
        adapter = get_adapter(engine)

        tokens = [self.name, adapter.type_to_sql(self.type, self.limit)]
        for k, v in self.options.items():
            result = adapter.column_option_to_sql(self.name, k, v)
            if result is None:
                continue
            elif isinstance(result, dict): # a way for column options to add constraints
                self.constraints.append(result['constraint'])
            else:
                tokens.append(result)
            
        return " ".join(tokens)
        
class Index:
    """Database index.
    
        >>> Index('user', 'email').sql('mock')
        'create index user_email_idx on user(email);'
        >>> Index('user', 'email', unique=True).sql('mock')
        'create unique index user_email_idx on user(email);'
        >>> Index('page', ['path', 'revision']).sql('mock')
        'create index page_path_revision_idx on page(path, revision);'
    """
    def __init__(self, table, columns, **options):
        self.table = table
        if not isinstance(columns, list):
            self.columns = [columns]
        else:
            self.columns = columns
            
        self.unique = options.get('unique')
        self.name = options.get('name')
        
    def sql(self, engine):
        adapter = get_adapter(engine)        
        name = self.name or adapter.index_name(self.table, self.columns)
        
        if self.unique:
            s = 'create unique index '
        else:
            s = 'create index '
        
        s += adapter.index_name(self.table, self.columns)
        s += ' on %s(%s);' % (self.table, ", ".join(self.columns))
        return s

def _test():
    """
    Define a sample schema.
    
        >>> s = Schema()
        >>> s.add_table('posts',
        ...     s.column('id', 'serial', primary_key=True),
        ...     s.column('slug', 'string', unique=True, null=False),
        ...     s.column('title', 'string', null=False),
        ...     s.column('body', 'text'),
        ...     s.column('created_on', 'timestamp', default=s.CURRENT_UTC_TIMESTAMP))
        ...
        >>> s.add_table('comments',
        ...     s.column('id', 'serial', primary_key=True),
        ...     s.column('post_id', 'integer', references='posts(id)'),
        ...     s.column('comment', 'text'))
        ...
        >>> s.add_index('posts', 'slug')
    
    Validate postgres schema.
    
        >>> print s.sql('postgres')
        create table posts (
            id serial primary key,
            slug character varying(255) unique not null,
            title character varying(255) not null,
            body text,
            created_on timestamp default (current_timestamp at time zone 'utc')
        );
        create table comments (
            id serial primary key,
            post_id int references posts(id),
            comment text
        );
        create index posts_slug_idx on posts(slug);
    
    Validate MySQL schema.
    
        >>> print s.sql('mysql')
        create table posts (
            id int auto_increment not null primary key,
            slug varchar(255) unique not null,
            title varchar(255) not null,
            body text,
            created_on datetime default UTC_TIMESTAMP
        );
        create table comments (
            id int auto_increment not null primary key,
            post_id int,
            comment text,
            foreign key (post_id) references posts(id)
        );
        create index posts_slug_idx on posts(slug);
    
    Thats all.
    """
    
if __name__ == "__main__":
    register_adapter('mock', MockAdapter)    
    
    import doctest
    doctest.testmod()
