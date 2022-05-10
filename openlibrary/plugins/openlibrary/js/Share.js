export function initShareModal($modalLinks){
    $modalLinks.each(function() {
        this.addEventListener('click', function() {
            $.colorbox({
                inline: true,
                opacity: '0.5',
                href: '#social-modal-content',
                width: '100%',
                maxWidth: '400px'
            });
        })
    })
}
