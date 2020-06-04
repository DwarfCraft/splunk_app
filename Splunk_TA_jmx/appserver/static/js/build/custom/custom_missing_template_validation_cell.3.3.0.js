define([
  "jquery",
  "underscore",
  "backbone",
  'splunkjs/mvc',
  "contrib/text!./templates/missingAccountAuthConfig.html",
  "contrib/jg_lib/utils/StringUtil"
], function (
  $,
  _,
  Backbone,
  mvc,
  missingAccountAuthConfig,
  StringUtil
) {
    "use strict";
    /**
     * Custom Row Cell
     * @constructor
     * @param {Object} globalConfig - Global configuration.
     * @param {string} serviceName - Input service name.
     * @param {element} el - The element of the custom cell.
     * @param {string} field - The cell field name.
     * @param {model} model - Splunk backbone model for the stanza.
     */
    let CustomTemplateCell = Backbone.View.extend({
      constructor: function (globalConfig, serviceName, el, field, model) {
        this.setElement(el);
        this.field = field;
        this.model = model;
        this.serviceName = serviceName;
        this.globalConfig = globalConfig;
        this.service = mvc.createService();
      },

      render: function () {

        var model = this.model;
        var html = '';
        var templateString = model.entry.content.get('templates');

        // Check input connect template is missing or not.
        if (templateString === undefined) {

          // Provide alert icon on template column if missing template found in input row.
          html = this.missingAccountAuthConfigTemplate({
            title: StringUtil.escapeHTML(model.entry.get('name')),
            account: '',
			flag: 'template'
          });
        } else {
          html = templateString;
        }

        this.$el.html(html);
        return this;

      },

      // Load template for missing template
      missingAccountAuthConfigTemplate: _.template(missingAccountAuthConfig)
    });

    return CustomTemplateCell;
  });