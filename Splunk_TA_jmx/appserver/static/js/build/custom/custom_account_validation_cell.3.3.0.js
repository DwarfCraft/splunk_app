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
    let CustomServerNameCell = Backbone.View.extend({
      constructor: function (globalConfig, serviceName, el, field, model) {
        this.setElement(el);
        this.field = field;
        this.model = model;
        this.serviceName = serviceName;
        this.globalConfig = globalConfig;
        this.service = mvc.createService();
      },

      render: function () {

        var serviceName = this.serviceName;
        var model = this.model;
        var inputName = model.entry.attributes['name'];
        var html = '';

        // Check the missing server account configuration for server and input page.
        if (serviceName === 'server') {
          var acccountName = model.entry.content.get("account_name");
          // Using server configuration has_account and account_name field to identify the account configuration is missing or not.
          if (parseInt(model.entry.content.get("has_account")) === 1 && acccountName === undefined) {

            // Provide alert icon on server column if missing account configuration found in server row.
            html = this.missingAccountAuthConfigTemplate({
              title: StringUtil.escapeHTML(model.entry.get('name')),
              account: acccountName,
			  flag: 'account'
            });
          } else {
            html = acccountName;
          }

        } else {

          var serverString = model.entry.content.attributes.servers;
          var notConfigureServers = model.entry.content.attributes.not_configure_servers;

          // Check input connect servers configuration is missing or not.
          if (notConfigureServers !== undefined && notConfigureServers !== '') {
            html = this.missingAccountAuthConfigTemplate({
              title: StringUtil.escapeHTML(notConfigureServers),
              account: serverString,
			  flag: 'account'
            });
          } else if (serverString === undefined) {

            // Provide alert icon on server column if missing server found in input row.
            html = this.missingAccountAuthConfigTemplate({
              title: StringUtil.escapeHTML(model.entry.get('name')),
              account: '',
			  flag: 'server'
            });
          } else {
            html = serverString;
          }

        }

        this.$el.html(html);
        return this;

      },

      // Load template for missing configuration
      missingAccountAuthConfigTemplate: _.template(missingAccountAuthConfig)
    });

    return CustomServerNameCell;
  });