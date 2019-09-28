/*
 * FIXME: The methods loadEditionsGraph, plot_minigraph and plot_tooltip_graph
 * need to be refactored once unit tests have been added to the repo. They
 * duplicate a lot of functionality
 */
// jquery-flot 0.7.0
import '../../../../../vendor/js/flot/jquery.flot.js';
import '../../../../../vendor/js/flot/jquery.flot.selection.js';
import '../../../../../vendor/js/flot/jquery.flot.crosshair.js';
import '../../../../../vendor/js/flot/jquery.flot.stack.js';
import '../../../../../vendor/js/flot/jquery.flot.pie.js';

/**
 * A special graph loaded on the following URLs:
 * - http://localhost:8080/subjects/fantasy#sort=date_published&ebooks=true
 * - http://localhost:8080/publishers/Barnes_&_Noble
 */
export function loadEditionsGraph() {
    var data, options, placeholder,
        plot, dateFrom, dateTo, previousPoint;
    data = [{data: JSON.parse(document.getElementById('graph-json-chartPubHistory').textContent)}];
    options = {
        series: {
            bars: {
                show: true,
                fill: 0.6,
                color: '#615132',
                align: 'center'
            },
            points: {
                show: true
            },
            color: '#615132'
        },
        grid: {
            hoverable: true,
            clickable: true,
            autoHighlight: true,
            tickColor: '#d9d9d9',
            borderWidth: 1,
            borderColor: '#d9d9d9',
            backgroundColor: '#fff'
        },
        xaxis: { tickDecimals: 0 },
        yaxis: { tickDecimals: 0 },
        selection: { mode: 'xy', color: '#00636a' },
        crosshair: {
            mode: 'xy',
            color: 'rgba(000, 099, 106, 0.4)',
            lineWidth: 1
        }
    };

    placeholder = $('#chartPubHistory');
    function showTooltip(x, y, contents) {
        $(`<div id="chartLabel">${contents}</div>`).css({
            position: 'absolute',
            display: 'none',
            top: y + 12,
            left: x + 12,
            border: '1px solid #615132',
            padding: '2px',
            'background-color': '#fffdcd',
            color: '#615132',
            'font-size': '11px',
            opacity: 0.90
        }).appendTo('body').customFadeIn(200);
    }
    previousPoint = null;
    placeholder.bind('plothover', function (event, pos, item) {
        var x, y;
        $('#x').text(pos.x.toFixed(0));
        $('#y').text(pos.y.toFixed(0));
        if (item) {
            if (previousPoint != item.datapoint) {
                previousPoint = item.datapoint;
                $('#chartLabel').remove();
                x = item.datapoint[0].toFixed(0);
                y = item.datapoint[1].toFixed(0);
                if (y == 1) {
                    showTooltip(item.pageX, item.pageY,
                        `${y} $_('edition in') ${x}`);
                } else {
                    showTooltip(item.pageX, item.pageY,
                        `${y} $_('editions in') ${x}`);
                }
            }
        }
        else {
            $('#chartLabel').remove();
            previousPoint = null;
        }
    });
    plot = $.plot(placeholder, data, options);
    dateFrom = plot.getAxes().xaxis.min.toFixed(0);
    dateTo = plot.getAxes().xaxis.max.toFixed(0);

    if (jQuery.support.opacity) {
        $('.chartYaxis').css({top: '60px', left: '-60px'})
    } else {
        $('.chartYaxis').css({top: '0', left: '0'})
    }

    if (dateFrom == (dateTo - 1)) {
        $('.clickdata').text(`$_('published in') ${dateFrom}`);
    } else {
        $('.clickdata').text(`$_('published between') ${dateFrom} & ${dateTo-1}.`);
    }
}

export function plot_minigraph(node, data) {
    var options = {
        series: {
            lines: {
                show: true,
                fill: 0,
                color: '#748d36'
            },
            points: {
                show: false
            },
            color: '#748d36'
        },
        grid: {
            hoverable: false,
            show: false
        }
    };
    $.plot(node, [data], options);
}

export function plot_tooltip_graph(node, data, tooltip_message, color='#748d36') {
    var i, options, graph;
    // empty set of rows. Escape early.
    if (!data.length) {
        return;
    }
    for (i = 0; i < data.length; ++i) {
        data[i][0] += 60 * 60 * 1000;
    }

    options = {
        series: {
            bars: {
                show: true,
                fill: 1,
                fillColor: color,
                color,
                align: 'left',
                barWidth: 24 * 60 * 60 * 1000
            },
            points: {
                show: false
            },
            color
        },
        grid: {
            hoverable: true,
            show: false
        },
        xaxis: {
            mode: 'time'
        }
    };

    graph = $.plot(node, [data], options);

    function showTooltip(x, y, contents) {
        $(`<div id="chartLabelA">${contents}</div>`).css({
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
        }).appendTo('body').fadeIn(200);
    }
    node.bind('plothover', function (event, pos, item) {
        var date, milli, x, y;
        $('#x').text(pos.x);
        $('#y').text(pos.y.toFixed(0));
        if (item) {
            $('#chartLabelA').remove();
            milli = item.datapoint[0];
            date = new Date(milli);
            x = date.toDateString();
            y = item.datapoint[1].toFixed(0);
            showTooltip(item.pageX, item.pageY, `${y} ${tooltip_message} ${x}`);
        } else {
            $('#chartLabelA').remove();
        }
    });
    return graph;
}

/**
 * Render a graph inside an element which has the id attribute.
 * @param {string} id of graph element
 * @param {Object} [options] to be passed to the $.plot method. Ignored if tooltip method passed
 * @param {string} [tooltip_message] to display when the graph is hovered over.
 * @param {string} [color] in hexidecimal to apply to the bars of a tooltip graph.
 *  Ignored if options and no tooltip_message is passed.
 */
export function loadGraph(id, options = {}, tooltip_message = '', color = null) {
    let data;
    const node = document.getElementById(id);
    const graphSelector = `graph-json-${id}`;
    const dataSource = document.getElementById(graphSelector);
    if (!node) {
        throw new Error(
            `No graph associated with ${id} on the page.`
        );
    }
    if(!dataSource) {
        throw new Error(
            `No data associated with ${id} - make sure a script tag with type text/json and id "${graphSelector}" is present on the page.`
        );
    } else {
        try {
            data = JSON.parse(dataSource.textContent);
        } catch (e) {
            throw new Error(`Unable to parse JSON in ${graphSelector}`);
        }
        if (tooltip_message) {
            return plot_tooltip_graph($(node), data, tooltip_message, color);
        } else {
            return $.plot($(node), data, options);
        }
    }
}

/**
 * Render a graph inside an element which has the id attribute.
 * @param {string} id of graph element
 * @param {Object} [options] to be passed to the $.plot method. Ignored if tooltip method passed
 * @param {string} [tooltip_message] to display when the graph is hovered over.
 * @param {string} [color] in hexidecimal to apply to the bars of a tooltip graph.
 *  Ignored if options and no tooltip_message is passed.
 */
export function loadGraphIfExists(id, options, tooltip_message, color) {
    if ($(`#${id}`).length) {
        loadGraph(id, options, tooltip_message, color);
    }
}
