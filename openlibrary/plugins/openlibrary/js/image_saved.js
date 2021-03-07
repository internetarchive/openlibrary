import { updateImage } from './image_change';

export function initImageSaved() {
    // Pull data from data-config of class "imageSaved" in covers/saved.html
    var image_and_imageid = $(".imageSaved").attr("data_config");

    $("#popClose").click(closePopup);
    updateImage(image_and_imageid);
}
