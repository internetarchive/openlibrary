import { plot_tooltip_graph } from './plot';
import '../../../../static/css/components/Tooltip--js.less';
import data from './graphs/data.js';
import options from './graphs/options.js';

function showTooltip(x, y, contents) {
    $(`<div id="tooltip">${contents}</div>`).css( {
        position: 'absolute',
        display: 'none',
        top: y + 5,
        left: x + 5,
        border: '1px solid #fdd',
        padding: '2px',
        'background-color': '#fee',
        opacity: 0.80
    }).appendTo('body').fadeIn(200);
}

// helper for returning the weekends in a period
function weekendAreas(axes) {
    var i, markings = [];
    var d = new Date(axes.xaxis.min);
    // go to the first Saturday
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 1) % 7))
    d.setUTCSeconds(0);
    d.setUTCMinutes(0);
    d.setUTCHours(0);
    i = d.getTime();
    do {
        // when we don't set yaxis, the rectangle automatically
        // extends to infinity upwards and downwards
        markings.push({ xaxis: { from: i, to: i + 2 * 24 * 60 * 60 * 1000 } });
        i += 7 * 24 * 60 * 60 * 1000;
    } while (i < axes.xaxis.max);

    return markings;
}

function initDashboard() {
    var previousPoint;
    $.getJSON('/admin/ipstats', function(data) {
        var i, options, d = data.data;

        // convert seconds into milliseconds
        for (i = 0; i < d.length; i++) {
            d[i][0] = d[i][0] * 1000;
        }

        // first correct the timestamps - they are recorded as the daily
        // midnights in UTC+0100, but Flot always displays dates in UTC
        // so we have to add one hour to hit the midnights in the plot
        for (i = 0; i < d.length; ++i) {
            d[i][0] += 60 * 60 * 1000;
        }

        options = {
            xaxis: { mode: 'time' },
            selection: { mode: 'x' },
            crosshair: { mode: 'x' },
            grid: { markings: weekendAreas, hoverable: true, backgroundColor: '#fff' },
            lines: { show: true },
            points: { show: true }
        };

        $(function() {
            var overview, plot = $.plot($('#placeholder'), [d], options);

            overview = $.plot($('#overview'), [d], {
                series: {
                    lines: { show: true, lineWidth: 1 },
                    shadowSize: 0
                },
                xaxis: { ticks: [], mode: 'time' },
                yaxis: { ticks: [], min: 0, autoscaleMargin: 0.1 },
                selection: { mode: 'x' }
            });

            // now connect the two
            $('#placeholder').bind('plotselected', function (event, ranges) {
                // do the zooming
                plot = $.plot($('#placeholder'), [d],
                    $.extend(true, {}, options, {
                        xaxis: { min: ranges.xaxis.from, max: ranges.xaxis.to }
                    })
                );

                // don't fire event on the overview to prevent eternal loop
                overview.setSelection(ranges, true);
            });

            $('#overview').bind('plotselected', function (event, ranges) {
                plot.setSelection(ranges);
            });
        });
    });

    previousPoint = null;
    $('#placeholder').bind('plothover', function (event, pos, item) {
        var y;
        $('#x').text(pos.x.toFixed(2));
        $('#y').text(pos.y.toFixed(2));

        if (item) {
            if (previousPoint != item.datapoint) {
                previousPoint = item.datapoint;

                $('#tooltip').remove();
                y = item.datapoint[1].toFixed(2);

                showTooltip(item.pageX, item.pageY, y);
            }
        } else {
            $('#tooltip').remove();
            previousPoint = null;
        }
    });
}

function plotGraphs() {
    if ($('#editgraph').length) {
        const humanEdits = JSON.parse($('#json-stats-human-edits').text());
        const members = JSON.parse($('json-stats-members').text());
        plot_tooltip_graph($('#editgraph'), humanEdits, 'edit(s) on');
        plot_tooltip_graph($('#membergraph'), members, 'new members(s) on');
    }
    if ($('#works_minigraph').length) {
        plot_tooltip_graph ($('#works_minigraph'), JSON.parse($('#json-works-counts').text()), ' works on ');
        plot_tooltip_graph ($('#editions_minigraph'), JSON.parse($('#json-editions-counts').text()), ' editions on ');
        plot_tooltip_graph ($('#covers_minigraph'), JSON.parse($('#json-covers-counts').text()), ' covers on ');
        plot_tooltip_graph ($('#authors_minigraph'), JSON.parse($('#json-authors-counts').text()), ' authors on ');
        plot_tooltip_graph ($('#lists_minigraph'), JSON.parse($('#json-lists-counts').text()), ' lists on ');
        plot_tooltip_graph ($('#members_minigraph'), JSON.parse($('#json-members-counts').text()), ' members on ');
    }
    $.plot('#books-added-per-day', [{
        data: JSON.parse($('#json-books-imported-daily').text())
    }], options.booksAdded);
    $.plot('#loans-per-day', data.loans, options.loans);
}

$( function () {
    initDashboard();
    plotGraphs();
});
