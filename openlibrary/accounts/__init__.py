
def login( username, password, remember=False):
    return self._request('/account/login', 'POST', dict(username=username, password=password))
    
def register( username, displayname, email, password):
    data = dict(username=username, displayname=displayname, email=email, password=password)
    _run_hooks("before_register", data)
    return self._request('/account/register', 'POST', data)

def activate_account( username):
    data = dict(username=username)
    return self._request('/account/activate', 'POST', data)
    
def update_account( username, **kw):
    """Updates an account.
    """
    data = dict(kw, username=username)
    return self._request('/account/update', 'POST', data)
    
def find_account( username=None, email=None):
    """Finds account by username or email."""
    if username is None and email is None:
        return None
    data = dict(username=username, email=email)
    return self._request("/account/find", "GET", data)    

def update_user( old_password, new_password, email):
    return self._request('/account/update_user', 'POST', 
        dict(old_password=old_password, new_password=new_password, email=email))
        
def update_user_details( username, **kw):
    params = dict(kw, username=username)
    return self._request('/account/update_user_details', 'POST', params)
    
def find_user_by_email( email):
    return self._request('/account/find_user_by_email', 'GET', {'email': email})
        
def get_reset_code( email):
    """Returns the reset code for user specified by the email.
    This called to send forgot password email. 
    This should be called after logging in as admin.
    """
    return self._request('/account/get_reset_code', 'GET', dict(email=email))
    
def check_reset_code( username, code):
    return self._request('/account/check_reset_code', 'GET', dict(username=username, code=code))
    
def get_user_email( username):
    return self._request('/account/get_user_email', 'GET', dict(username=username))
    
def reset_password( username, code, password):
    return self._request('/account/reset_password', 'POST', dict(username=username, code=code, password=password))

def get_user(self):
    # avoid hitting infobase when there is no cookie.
    if web.cookies().get(config.login_cookie_name) is None:
        return None
    try:
        data = self._request('/account/get_user')
    except ClientException:
        return None
        
    user = data and create_thing( data['key'], self._process_dict(common.parse_query(data)))
    return user
