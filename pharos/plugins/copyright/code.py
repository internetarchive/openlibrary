import copyrightstatus

@view.public
def copyright_status(edition):
    return copyrightstatus.copyright_status(edition)
