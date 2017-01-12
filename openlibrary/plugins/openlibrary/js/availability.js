$(function(){
    var getAvailability = function(ocaids, callback) {
        var url = '/availability';
        $.ajax({
            url: url,
            type: "POST",
            data: JSON.stringify({
                "ocaids": ocaids
            }),
            dataType: "json",
	    contentType: "application/json",
            beforeSend: function(xhr) {
                xhr.setRequestHeader("Content-Type", "application/json");
                xhr.setRequestHeader("Accept", "application/json");
            },
            success: function(result) {
                return callback(result);
            }
        });
    };
    
    var ocaids = [];
    $('[ocaid]').each(function(index, elem) {
	var ocaid = $(elem).attr('ocaid');
	ocaids.push(ocaid);
	console.log(ocaid);
    });
    
    getAvailability(ocaids, function(response) {
	console.log(response);
    });
});
