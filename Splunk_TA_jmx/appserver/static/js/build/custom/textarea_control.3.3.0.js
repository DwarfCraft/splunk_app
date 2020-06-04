define(["jquery", "underscore", "backbone", "moment", "splunkjs/mvc"], function(
  $,
  _,
  Backbone,
  momen,
  mvc
) {
  class CustomComponent {
    /**
     * Custom Component
     * @constructor
     * @param {Object} globalConfig - Global configuration.
     * @param {string} serviceName - Service name.
     * @param {element} el - The element of the custom row.
     * @param {string} modelAttribute - Backbone model attribute name.
     * @param {object} model - Backbone model for form, not Splunk model
     * @param {object} util - {
                displayErrorMsg,
                addErrorToComponent,
                removeErrorFromComponent
            }.
     * @param {string} action - action: create/edit/clone/delete
     */
    constructor(
      globalConfig,
      serviceName,
      el,
      modelAttribute,
      model,
      util,
      action
    ) {
      this.globalConfig = globalConfig;
      this.el = el;
      this.serviceName = serviceName;
      this.modelAttribute = modelAttribute;
      this.model = model;
      this.util = util;
      this.action = action;
    }
    render() {
      var value = "";
      if (this.model.get(this.modelAttribute)) {
        value = this.model.get(this.modelAttribute);
      }
      var model_json = {};
      model_json["content"] = value;
      model_json["id"] = this.serviceName + "-" + this.modelAttribute;
      model_json["name"] = this.modelAttribute;

      var content_html_template = `<div class="form-horizontal form-small content">
            <div class="form-group control-group"><div class="control-label col-sm-2">
                <p> Content  </p>
            </div>
            <div class="col-sm-10 controls control-placeholder">
                <div class="control shared-controls-textcontrol control-default" >
                    <span class="uneditable-input " data-role="uneditable-input" style="display:none"></span>
                    <textarea id="<%- id %>" name="<%- name %>" rows="4" cols="50"><%- content %></textarea>
                </div>
            </div>
        </div>`;
      var content_template = _.template(content_html_template);
      this.el.innerHTML = content_template(model_json);
      var el = this.el.querySelector("#" + model_json["id"]);

      el.addEventListener("change", () => {
        this.model.set(this.modelAttribute, el.value);
      });
      return this;
    }
  }

  return CustomComponent;
});
