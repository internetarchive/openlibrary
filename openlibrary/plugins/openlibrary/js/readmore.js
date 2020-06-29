export function initReadMoreButton() {

    function AddReadMore() {
        //This limit you can set after how much characters you want to show Read More.
        var carLmt = 160;
        // Text to show when text is collapsed
        var readMoreTxt = ' ... <br> Read More';
        // Text to show when text is expanded
        var readLessTxt = ' <br> Read Less';

        var allstr, firstSet, secdHalf, strtoadd;
        //Traverse all selectors with this class and manupulate HTML part to show Read More
        $('.addReadMore').each(function() {
            if ($(this).find('.firstSec').length)
                return;

            allstr = $(this).text();
            if (allstr.length > carLmt) {
                firstSet = allstr.substring(0, carLmt);
                secdHalf = allstr.substring(carLmt, allstr.length);
                strtoadd = firstSet + 
                           `<span class='SecSec'>` + 
                           secdHalf + 
                           `</span><span class='readMore'  title='Click to Show More'>` + 
                           readMoreTxt + `</span><span class='readLess' title='Click to Show Less'>` + 
                           readLessTxt + '</span>';
                $(this).html(strtoadd);
            }

        });
        //Read More and Read Less Click Event binding
        $(document).on('click', '.readMore,.readLess', function() {
            $(this).closest('.addReadMore').toggleClass('showlesscontent showmorecontent');
        });
    }

    $(function() {
        //Calling function after Page Load
        AddReadMore();
    });
    
    var el, ps, up, totalHeight, p;
    $('.sidebar-box .button').click(function() {
        totalHeight = 0

        el = $(this);
        p  = el.parent();
        up = p.parent();
        ps = up.find(`p:not('.read-more')`);

        // measure how tall inside should be by adding together heights of all inside paragraphs (except read-more paragraph)
        ps.each(function() {
        totalHeight += $(this).outerHeight();
        });
   
        up
        .css({
            // Set height to prevent instant jumpdown when max height is removed
            'height': up.height(),
            'max-height': 9999
        })
        .animate({
            'height': totalHeight
        });

        // fade out read-more
        p.fadeOut();

        // prevent jump-down
        return false;

    });
}
