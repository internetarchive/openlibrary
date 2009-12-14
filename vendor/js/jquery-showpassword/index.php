<html>
<head>
<title>jQuery showPassword Plugin</title>
<script type="text/javascript" src="http://ajax.googleapis.com/ajax/libs/jquery/1.3/jquery.min.js"></script>
<script type="text/javascript" src="jquery.showpassword.js"></script>
<script type="text/javascript">

$(document).ready(function(){
	$('#testpassword1').showPassword();
	$('#testpassword').showPassword('.checker', { text: 'Custom Show Password Text', name: 'showmypass' });
		
});

</script>
<style>
body { font-family: Arial, Helvetica, serif, sans-serif; }
form { margin: 15px 0; padding: 15px; background: #ccc; color: #000; border: 1px solid #aaa; width: 500px; }
form label.form { float: left; width: 120px; display: block; }
form input#testpassword1, form input#testpassword { float: left; display: block; }
.clear { clear: both; }
div.checker { clear: both; display: block; border: 1px dotted #2d2d2d; color: #2d2d2d; background: transparent; width: 230px; font-size: 0.8em; margin: 20px 0 0 0; }
</style>
</head>
<body>

	<h1>jQuery showPassword Plugin - Simple</h1>
	<p>This is the simplest method of invoking the plugin and adds a check box directly after the password input.<br />
	<strong>Usage:</strong><pre>$('#testpassword1').showPassword();</pre></p>
	
	<form method="post" action="#" id="myform1">
		<label class="form" for="myname1">name:</label>
		<input type="name" name="myname1" id="myname1" value="" />
		<div class="clear"></div>
		<label class="form" for="testpassword1">password: </label>
		<input type="password" name="mypassword1" value="" id="testpassword1" />
	</form>
	
	<h1>jQuery showPassword Plugin - Customized</h1>
	<p>This is the using the customizable option when invoking the plugin method of and it injects a check box into a specified element.<br />
	<strong>Usage:</strong><pre>$('#testpassword').showPassword('.checker', { text: 'Custom Show Password Text', name: 'showmypass' });</pre></p>
	
	<form method="post" action="#" id="myform">
		<label class="form" for="myname">name: </label>
		<input type="name" name="myname" id="myname" value="" />
		<div class="clear"></div>
		<label class="form" for="testpassword">password: </label>
		<input type="password" class="test" name="mypassword" value="" id="testpassword" />
		<div class="clear"></div>
		<div class="checker"></div>
	</form>

</body>
</html>