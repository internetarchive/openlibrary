export function initExportReadingLog() {
    var encodedUri, link;
    $('.readingLog_download').on('click', function () {
        $.ajax({
            url: '/account/export',
            type: 'GET',
            success: function (response) {
                let csvContent = 'data:text/csv;charset=utf-8,';
                var key;
                for (key in response) {
                    let row = response[key].join(',');
                    csvContent += `${row}\r\n`;
                }

                encodedUri = encodeURI(csvContent);
                link = document.createElement('a');
                link.setAttribute('href', encodedUri);
                link.setAttribute('download', 'OpenLibrary_ReadingLog.csv');
                document.body.appendChild(link);

                link.click();
            }
        });
    });
}
