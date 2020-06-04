define([
  "splunkjs/mvc",
  './utility.3.3.0'
], function (mvc) {
  class Hook {
    /**
     * Form hook
     * @constructor
     * @param {Object} globalConfig - Global configuration.
     * @param {object} serviceName - Service name
     * @param {object} model - Backbone model for form, not Splunk model
     * @param {object} util - {
                displayErrorMsg,
                addErrorToComponent,
                removeErrorFromComponent
            }.
     */
    constructor(globalConfig, serviceName, model, util) {
      this.globalConfig = globalConfig;
      this.serviceName = serviceName;
      this.model = model;
      this.util = util;
    }

    /**
     * On Create Event Handling control
     */
    onCreate() { }

    /**
     * On Render Event Handling control
     */
    onRender() {

      // Display/Remove the destination app field from UI based on setting configuration display_destination_app stanza show field.
      displayDestinationApp(mvc.createService(), ".destinationapp", this.model);
    }

    /**
     * Returns true if value is not set else false
     * @param {string} value
     */
    isEmpty(value) {
      return value === undefined || value.trim().length === 0;
    }

    /**
     * Returns label for given field else returns default string 'No label found'
     * @param {string} field
     */
    getFieldLabel(field) {
      for (var x of this.globalConfig["pages"]["configuration"]["tabs"][1][
        "entity"
      ]) {
        if (field === x["field"]) return x["label"];
      }
      return null;
    }

    /**
     * Call displayErrorMsg for first unset value for requiredFields element and returns true else returns false
     * @param {Array} requiredFields
     */
    isEmptyRequiredFields(requiredFields) {
      for (var field of requiredFields) {
        if (this.isEmpty(this.model.get(field))) {
          this.util.displayErrorMsg(
            `Field ${this.getFieldLabel(field)} is required`
          );
          return true;
        }
      }
      return false;
    }

    /**Put form validation logic here.
     * Return true if validation pass, false otherwise.
     * Call displayErrorMsg when validation failed.
     */
    onSave() {

      // Set the default destination app field value when destination app field not found in model.
      if (this.model.get('destinationapp') === undefined) {
        this.model.set('destinationapp', 'Splunk_TA_jmx')
      }
      return true;
    }
    // Action needs to perform after success operation
    onSaveSuccess() { }
    // Action needs to perform on save failure
    onSaveFail() { }
  }
  return Hook;
});
