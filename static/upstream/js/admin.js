function plot_tooltip_graph(node, data, tooltip_message) {
    for (var i = 0; i < data.length; ++i)
	data[i][0] += 60 * 60 * 1000;

    var options = {
	series: {
            bars: {
                show: true,
                fill: 1,
                fillColor: "#748d36",
                color: "#748d36",
                align: "left",
                barWidth: 24 * 60 * 60 * 1000
            },
            points: {
                show: false
            },
            color: "#748d36"
        },
        grid: {
            hoverable: true,
            show: false
        },
        xaxis: {
            mode: "time"
        }
    };

    var plot = $.plot(node, [data], options);

    function showTooltip(x, y, contents) {
        $('<div id="chartLabelA">' + contents + '</div>').css( {
            position: 'absolute',
            display: 'none',
            top: y + 12,
            left: x + 12,
            border: '1px solid #ccc',
            padding: '2px',
            backgroundColor: '#efefef',
            color: '#454545',
            fontSize: '11px',
            webkitBoxShadow: '1px 1px 3px #333',
            mozBoxShadow: '1px 1px 1px #000',
            boxShadow: '1px 1px 1px #000'
        }).appendTo("body").fadeIn(200);
    };
    var previousPoint = null;
    node.bind("plothover", function (event, pos, item) {
        $("#x").text(pos.x);
        $("#y").text(pos.y.toFixed(0));
        if (item) {
            $("#chartLabelA").remove();
            var milli = item.datapoint[0];
            var date = new Date(milli);
            var x = date.toDateString(),
            y = item.datapoint[1].toFixed(0);
            showTooltip(item.pageX, item.pageY, y + " "+ tooltip_message +" " + x);
        } else {
            $("#chartLabelA").remove();
        };
    });
}

function plot_minigraph(node, data) {
      var options = {
       series: {
            lines: {
                show: true,
                fill: 1,
                fillColor: "#748d36",
                color: "#748d36"
            },
            points: {
                show: false
            },
            color: "#748d36"
        },
        grid: {
            hoverable: true,
            show: false
        }
    };
    $.plot(node, [data], options);
}
