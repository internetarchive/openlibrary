const booksAdded = {
    series: {
        stack: 0,
        bars: {
            show: true,
            align: 'left',
            barWidth: 20 * 60 * 60 * 1000,
        },
    },
    grid: {
        hoverable: true,
        show: true,
        borderWidth: 1,
        borderColor: '#d9d9d9'
    },
    xaxis: {
        mode: 'time'
    },
    legend: {
        show: true,
        position: 'nw'
    }
};

const loans = {
    series: {
        stack: 0,
        bars: {
            show: true,
            align: 'left',
            barWidth: 20 * 60 * 60 * 1000,
        },
    },
    grid: {
        hoverable: true,
        show: true,
        borderWidth: 1,
        borderColor: '#d9d9d9'
    },
    xaxis: {
        mode: 'time'
    },
    yaxis: {
        position: 'right'
    },
    legend: {
        show: true,
        position: 'nw'
    }
};

export default {
    booksAdded,
    loans
};
