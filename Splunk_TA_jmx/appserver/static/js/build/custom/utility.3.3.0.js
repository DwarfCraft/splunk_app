/**
 * Display/Remove the destinationapp input based on splunk_ta_jmx_settings.conf file define display_destination_app stanza show filed.
 * @method displayDestinationApp
 * @param {service} splunk mvc service which used for rest call.
 * @param {attribute} id or class attribute value
 *  To pass id attribute, use hash (#) character, followed by the id value of the attribute
 *  To pass class attribute, use hash (.) character, followed by the class value of the attribute
 * @param {model} Backbone model for form, not Splunk model
 */
function displayDestinationApp(service, attribute, model) {

  /**
   * Form edit mode remove destination app field from UI.
   * Form create mode call the setting rest handler to get display_destination_app stanza show value and based on that value show/remove destination app field.
   */
  if (model.get('name')) {
    removeElement(attribute);
  } else {

    service.get('/splunk_ta_jmx_settings/general', {}, (err, response) => {
      if (!parseInt(response.data.entry[0].content.display_destination_app)) {
        removeElement(attribute);
      }
    });
  }

}

/**
 * Based on attribute value remove the element from UI.
 * @method removeElement
 * @param {attribute} id or class attribute value
 *  To pass id attribute, use hash (#) character, followed by the id value of the attribute
 *  To pass class attribute, use hash (.) character, followed by the class value of the attribute
 */
function removeElement(attribute) {

  $(attribute).remove()
}