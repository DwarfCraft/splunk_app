define([
  "jquery",
  "underscore",
  "splunkjs/mvc",
  "contrib/text!./templates/messageLoading.html",
  "contrib/text!./templates/messageWarning.html",
  "./jquery.dataTables.min",
  "css!./jquery.dataTables.min",
  './utility.3.3.0'
], function ($, _, mvc, messageLoading, messageWarning) {
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

      // To achieve validation for data duplication, flow for "on save" has been manipulated
      $(".submit-btn").hide();
      $(".modal-footer").append(
        `<input type="button" id="add-button" class="btn btn-primary" value="` +
        $(".submit-btn").val() +
        `">`
      );
      $("#add-button").click(() => {
        this._doValidation();
      });
      // Handle the input field enter key press event.
      $(".modal-content").keypress((event) => {
        if (event.which == 13) {
          event.preventDefault();
          this._doValidation();
        }
      });
    }

    /*
     * Custom validations covers all default UI validation and data duplication validation too
     */
    _doValidation() {

      // Set the default destination app field value when destination app field not found in model.
      if (this.model.get('destinationapp') === undefined) {
        this.model.set('destinationapp', 'Splunk_TA_jmx')
      }

      $("input").removeClass("validation-error");
      $("ul").removeClass("validation-error");

      this.model.set(
        "servers",
        this.getPipeDelimiterValue(".serversDataTable")
      );
      this.model.set(
        "templates",
        this.getPipeDelimiterValue(".templatesDataTable")
      );
      var serversDetails = this.model.get("servers");
      var templatesDetails = this.model.get("templates");
      if (serversDetails == undefined || serversDetails.trim().length == 0) {
        this.util.displayErrorMsg("Atleast one server must be selected");
        return;
      } else if (templatesDetails == undefined ||
        templatesDetails.trim().length == 0
      ) {
        this.util.displayErrorMsg("Atleast one template must be selected");
        return;
      }

      // Calling service endpoint to validate whether data duplication will happen or not
      var service = mvc.createService();

      var data = {
        templates: this.model.get("templates"),
        servers: this.model.get("servers"),
        input_name: this.model.get("name")
      };

      $(".modal-body > .msg").remove();
      $(".modal-body").prepend(
        _.template(messageLoading)({ message: "Saving..." })
      );

      service.get(
        "/services/splunk_ta_jmx_rh_validate_input_data_duplication",
        data,
        (err, response) => {
          if (!err &&
            response.data.entry[0].content.duplicate_warning == true
          ) {
            $(".modal-body > .msg").remove();
            $(".modal-body").prepend(
              _.template(messageWarning)({
                message:
                  "Selected servers and templates can cause data duplication. For more information, see the ta_jmx_rh_input_data_duplication.log file. To continue, click confirm."
              })
            );

            $(".modal-body :input").attr("disabled", "disabled");
            $(".msg-body > .close").attr("disabled", false);

            $(".cancel-btn").hide();
            $("#add-button").hide();
            $(".submit-btn")
              .show()
              .attr("value", "Confirm");

            if ($("#cancel-button").length) {
              $("#cancel-button").show();
            } else {
              $(".modal-footer").append(
                `<input type="button" id="cancel-button" class="btn" value="Cancel">`
              );
            }

            $(".msg-body > .close").click(function () {
              $(".modal-body > .msg").remove();
            });

            $("#cancel-button").click(function () {
              $(".modal-body :input").attr("disabled", false);
              $(".modal-body > .msg-loading").remove();
              $(".modal-body > .msg-warning").remove();
              $("#add-button").show();
              $(".cancel-btn").show();
              $("#cancel-button").hide();
              $(".submit-btn").hide();
            });
          } else {
            $(".submit-btn").trigger("click");
          }
        }
      );
    }

    /** For execute logic before save event.
     * Put form validation logic here.
     * @class Hook
     * @method onSave
     * @returns boolean (ture if validation pass, false otherwise)
     */
    onSave() {
      return true;
    }

    /**
     * Convert element list to Pipe separator string
     * @param {attribute} id or class attribute value
     *   To pass id attribute, use hash (#) character, followed by the id value of the attribute
     *   To pass class attribute, use hash (.) character, followed by the class value of the attribute
     * @return string
     *   return pipe separator string value
     */
    getPipeDelimiterValue(attribute) {
      let rows = $(attribute)
        .DataTable()
        .rows()
        .nodes();
      let valueArray = [];
      for (let i = 0; i < rows.length; i++) {
        if (rows[i].cells[0].getElementsByTagName("input")[0].checked) {
          valueArray.push(rows[i].cells[0].getElementsByTagName("input")[0].value);
        }
      }
      return valueArray.length > 0 ? valueArray.join(" | ") : "";
    }

    onSaveSuccess() { }

    onSaveFail() { }
  }
  return Hook;
});
