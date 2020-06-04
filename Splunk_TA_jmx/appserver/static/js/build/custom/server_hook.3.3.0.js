define([
  "jquery",
  "underscore",
  "splunkjs/mvc",
  './utility.3.3.0'
], function ($, _, mvc) {
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
      this.allConnectionTypeFields = [
        "pidCommand",
        "account_name",
        "account_password",
        "pid",
        "pidFile",
        "jmx_url",
        "host",
        "jmxport",
        "lookupPath",
        "stubSource",
        "encodedStub"
      ];
      this.processConnectionType = ["pidCommand", "pidFile", "pid"];
      this.protocolConnectionType = [
        "soap",
        "soapssl",
        "hessian",
        "hessianssl",
        "burlap",
        "burlapssl"
      ];
      this.protocolFields = [
        "account_name",
        "account_password",
        "host",
        "jmxport",
        "lookupPath"
      ];
      this.stubSourceFields = [
        "account_name",
        "account_password"
      ];
      this.urlFields = ["jmx_url", "account_name", "account_password"];
      this.allStubSourceFields = [
        "encodedStub",
        "host",
        "jmxport",
        "lookupPath"
      ];
      this.stubSource = {
        ior: ["encodedStub"],
        stub: ["encodedStub"],
        jndi: ["host", "jmxport", "lookupPath"]
      };
      this.showConnectionTypeFields = [];
      this.hideConnectionTypeFields = [];
      this.showStubSourceFields = [];
      this.hideStubSourceFields = [];
    }

    onCreate() { }

    /**
     * Returns an array containing two arrays one containing fields to be displayed
     * and other with fields to be hidden depended on Connection Type dropdown
     */
    _getConnectionTypeFields() {
      this.showConnectionTypeFields = [];
      this.hideConnectionTypeFields = [];
      var selectedConnectionType = this.model.get("protocol");
      if (selectedConnectionType != undefined) {
        if (this.processConnectionType.includes(selectedConnectionType)) {
          this.showConnectionTypeFields.push(selectedConnectionType);
        } else if (
          selectedConnectionType == "rmi" ||
          selectedConnectionType == "iiop"
        ) {

          this.showConnectionTypeFields = this.showConnectionTypeFields.concat(this.stubSourceFields);
          this.showConnectionTypeFields.push("stubSource");
        } else if (selectedConnectionType == "url") {
          this.showConnectionTypeFields = this.showConnectionTypeFields.concat(this.urlFields);
        } else if (
          this.protocolConnectionType.includes(selectedConnectionType)
        ) {
          this.showConnectionTypeFields = this.showConnectionTypeFields.concat(this.protocolFields);
        }
        this.hideConnectionTypeFields = _.difference(this.allConnectionTypeFields, this.showConnectionTypeFields);
      }
      return [this.showConnectionTypeFields, this.hideConnectionTypeFields];
    }

    /**
     * Show and hide connection type fields
     */
    _connectionTypeChange() {
      [this.showConnectionTypeFields, this.hideConnectionTypeFields] = this._getConnectionTypeFields();

      this.hideConnectionTypeFields.forEach((field) => {
        this._toggleField(field, "hide");
      });

      this.showConnectionTypeFields.forEach((field) => {
        this._toggleField(field, "show");
        this._hideOptionalText(field);
      });
    }

    /**
     * Returns an array containing two arrays one containing fields to be displayed
     * and other with fields to be hidden depended on Stub source dropdown
     */
    _getStubSourceFields() {
      var selectedStubSource = this.model.get("stubSource");
      this.showStubSourceFields = [];
      this.hideStubSourceFields = [];
      if (
        selectedStubSource != undefined &&
        this.stubSource[selectedStubSource] != undefined
      ) {
        this.showStubSourceFields = this.stubSource[selectedStubSource];
        this.hideStubSourceFields = _.difference(this.allStubSourceFields, this.showStubSourceFields);
      }
      return [this.showStubSourceFields, this.hideStubSourceFields];
    }

    /**
     * Show and hide stub source fields
     */
    _stubSourceChange() {
      [this.showStubSourceFields, this.hideStubSourceFields] = this._getStubSourceFields();
      this.showStubSourceFields.forEach((field) => {
        this._toggleField(field, "show");
        this._hideOptionalText(field);
      });
      this.hideStubSourceFields.forEach((field) => {
        this._toggleField(field, "hide");
      });
    }

    /**
     * Hide and show field using fieldname depending on action parameter
     * @param {string} fieldName
     * @param {string} action
     */
    _toggleField(fieldName, action) {
      if (action == "hide") {
        $(`div[class$='${fieldName}']`).hide();
      } else if (action == "show") {
        $(`div[class$='${fieldName}']`).show();
        if (fieldName === 'stubSource' && this.model.get(fieldName) !== '') {
          this._stubSourceChange();
        }
      }
    }

    /**
     * Removes "(optional)" text from the placeholder values for given fieldName
     * @param {string} fieldName
     */
    _hideOptionalText(fieldName) {
      var value = $(`#server-${fieldName}`).attr("placeholder");
      if (value != undefined) {
        value = value.replace("(optional)", "");
        $(`#server-${fieldName}`).attr("placeholder", value);
      }
    }

    /**
     * On Render Event Handling control
     */
    onRender() {

      // Display/Remove the destination app field from UI based on setting configuration display_destination_app stanza show field.
      displayDestinationApp(mvc.createService(), ".destinationapp", this.model);

      this.model.on(
        "change:protocol",
        function () {
          this._connectionTypeChange();
        },
        this
      );
      this.model.on(
        "change:stubSource",
        function () {
          this._stubSourceChange();
        },
        this
      );
      this._connectionTypeChange();

      // Set the protocol field value as `url` when we get jmx_url field value
      if (this.model.get('jmx_url') !== undefined && this.model.get('jmx_url') !== '') {
        this.model.set('protocol', 'url')
      }
    }

    /**
     * Returns label for given field else returns null
     * @param {string} field
     */
    getFieldLabel(field) {
      for (var x of this.globalConfig["pages"]["configuration"]["tabs"][0][
        "entity"
      ]) {
        if (field === x["field"]) return x["label"];
      }
      return null;
    }

    /**
     * Returns true if value is not set else false
     * @param {string} value
     */
    isEmpty(value) {
      return value === undefined || value.trim().length === 0;
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

      // Set the default destination app field value when the destination app field not found in the model.
      if (this.model.get('destinationapp') === undefined) {
        this.model.set('destinationapp', 'Splunk_TA_jmx')
      }

      var allRequiredFields = [
        "pidCommand",
        "pid",
        "pidFile",
        "jmx_url",
        "host",
        "jmxport",
        "stubSource",
        "encodedStub"
      ];

      var hideFields = _.difference(this.hideConnectionTypeFields, this.showStubSourceFields);
      hideFields = hideFields.concat(this.hideStubSourceFields);
      hideFields.forEach((field) => {
        this.model.unset(field);
        this.model.set(field, '');
      });

      var allDisplayedFields = this._getConnectionTypeFields()[0];
      allDisplayedFields = allDisplayedFields.concat(this._getStubSourceFields()[0]);

      var fieldsToCheck = allRequiredFields.filter(
        value => -1 !== allDisplayedFields.indexOf(value)
      );

      // Check all required field
      if (this.isEmptyRequiredFields(fieldsToCheck)) {
        return false;
      }

      //Check account name and account password combination
      var accountName = this.model.get("account_name");
      var password = this.model.get("account_password");
      if (!this.isEmpty(accountName) && this.isEmpty(password)) {
        this.util.displayErrorMsg(
          `Field ${this.getFieldLabel("account_password")} is required`
        );
        return false;
      }
      if (this.isEmpty(accountName) && !this.isEmpty(password)) {
        this.util.displayErrorMsg(
          `Field ${this.getFieldLabel("account_name")} is required`
        );
        return false;
      }

      // Get the lookupPath value from the model and check the first character is forward slash or not. if the first character is not forward slash then concat forward slash at the first position on lookupPath Value.
      var lookupPath = this.model.get("lookupPath");
      if (lookupPath !== undefined && lookupPath !== '' && lookupPath.charAt(0) !== '/') {
        this.model.set("lookupPath", '/' + lookupPath);
      }

      return true;
    }

    onSaveSuccess() { }
    onSaveFail() { }
  }
  return Hook;
});
