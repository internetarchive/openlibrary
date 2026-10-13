import $ from 'jquery';
import 'flot/jquery.flot.js';
import 'flot/jquery.flot.selection.js';
import 'flot/jquery.flot.crosshair.js';

/**
 * A special graph loaded on the following URLs:
 * - http://localhost:8080/subjects/fantasy#sort=date_published&ebooks=true
 * - http://localhost:8080/publishers/Barnes_&_Noble
 */
export function loadEditionsGraph() {
    var data, options, placeholder, plot, dateFrom, dateTo, previousPoint;
    data = [{ data: JSON.parse(document.getElementById('graph-json-chartPubHistory').textContent) }];
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
        $(`<div id="chartLabel" class="chart-tooltip">${contents}</div>`)
            .css({
                position: 'absolute',
                display: 'none',
                top: y + 12,
                left: x + 12,
                border: '1px solid #615132',
                padding: '2px',
                'background-color': '#fffdcd',
                color: '#615132',
                'font-size': '11px',
                opacity: 0.9
            })
            .appendTo('body')
            .fadeIn(200);
    }
    previousPoint = null;
    placeholder.bind('plothover', function (event, pos, item) {
        var x, y;
        $('#x').text(pos.x.toFixed(0));
        $('#y').text(pos.y.toFixed(0));
        if (item) {
            if (previousPoint !== item.datapoint) {
                previousPoint = item.datapoint;
                $('#chartLabel').remove();
                x = item.datapoint[0].toFixed(0);
                y = item.datapoint[1].toFixed(0);
                if (y === 1) {
                    showTooltip(item.pageX, item.pageY, `${y} edition in ${x}`);
                } else {
                    showTooltip(item.pageX, item.pageY, `${y} editions in ${x}`);
                }
            }
        } else {
            $('#chartLabel').remove();
            previousPoint = null;
        }
    });

    placeholder.bind('plotclick', function (event, pos, item) {
        if (item) {
            plot.unhighlight();
            const yearFrom = item.datapoint[0].toFixed(0);
            applyDateFilter(yearFrom, yearFrom);

            plot.highlight(item.series, item.datapoint);
        } else {
            plot.unhighlight();
        }
    });

    placeholder.bind('plotselected', function (event, ranges) {
        plot = $.plot(
            placeholder,
            data,
            $.extend(true, {}, options, {
                xaxis: { min: ranges.xaxis.from, max: ranges.xaxis.to },
                yaxis: { min: ranges.yaxis.from, max: ranges.yaxis.to }
            })
        );

        const yearFrom = ranges.xaxis.from.toFixed(0);
        const yearTo = ranges.xaxis.to.toFixed(0);
        applyDateFilter(yearFrom, yearTo);
    });

    function applyDateFilter(yearFrom, yearTo, hideSelector = '.chartUnzoom', showSelector = '.chartZoom') {
        document.dispatchEvent(new CustomEvent('filter', { detail: { yearFrom: yearFrom, yearTo: yearTo } }));
        $(hideSelector).hide();
        $(showSelector).removeClass('hidden').show();
    }

    plot = $.plot(placeholder, data, options);
    dateFrom = plot.getAxes().xaxis.min.toFixed(0);
    dateTo = plot.getAxes().xaxis.max.toFixed(0);

    $('.resetSelection').on('click', function () {
        plot = $.plot(placeholder, data, options);

        const yearFrom = plot.getAxes().xaxis.min.toFixed(0);
        const yearTo = plot.getAxes().xaxis.max.toFixed(0);
        applyDateFilter(yearFrom, yearTo, '.chartZoom', '.chartUnzoom');
    });

    $('.chartYaxis').css({ top: '60px', left: '-60px' });

    if (dateFrom === dateTo - 1) {
        $('.clickdata').text(`Published in ${dateFrom}`);
    } else {
        $('.clickdata').text(`Published between ${dateFrom} & ${dateTo - 1}.`);
    }
}
