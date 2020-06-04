define([
  'jquery',
  'underscore',
  'backbone',
  'moment',
  'splunkjs/mvc',
  "contrib/text!./templates/inputTab.html",
  "contrib/text!./templates/missingAccountAuthConfig.html",
  "contrib/jg_lib/utils/StringUtil"
], function ($, _, Backbone, momen, mvc, inputTab, missingAccountAuthConfig, StringUtil) {

  class CustomInputTab {
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
    constructor(globalConfig, serviceName, el, modelAttribute, model, util, action) {
      this.globalConfig = globalConfig;
      this.el = el;
      this.serviceName = serviceName;
      this.modelAttribute = modelAttribute;
      this.model = model;
      this.util = util;
      this.action = action;
      this.serverArray = this.model.get("servers");
      this.templateArray = this.model.get("templates");
      this.rowType = ["odd", "even"];
      this.service = mvc.createService();

      // Make configuration page base url using window location object property which we use in deep link URL.
      this.accountConfigURL = location.protocol + "//" + location.host + location.pathname.replace("inputs", "configuration");
    }

    /** For rendering the page
     * @class Hook
     * @method render
     */
    render() {

      this.serverArray = (this.serverArray != undefined) ? this.serverArray.replace(/ /g, '').split('|') : [];
      this.templateArray = (this.templateArray != undefined) ? this.templateArray.replace(/ /g, '').split('|') : [];

      this.service.get('/splunk_ta_jmx_server', {'count':0}, (err, response) => {
        this.renderServerHtml(response.data.entry);
      });

      this.service.get('/splunk_ta_jmx_template', {}, (err, response) => {
        this.renderTemplateHtml(response.data.entry);
      });

      this.el.innerHTML = this.renderTabs({});
      return this;
    }

    /** For rendering server HTML
     * @class Hook
     * @method renderServerHtml
     * @params serverData - Server List
     */
    renderServerHtml(serverData) {

      var serverDataRows = `<tr class="apps-table-tablerow ##type##" ><td class="bs-checkbox "><input name="btSelectItem" type="checkbox" value="##value##" ##checked##></td><td class="col-name">##alertIcon##<a class="external" href="` + this.accountConfigURL + `?tab=server&record=##name##" target="_blank">##name##</a></td><td class="col-description"> ##description## </td><td class="col-interval"> ##interval## </td><td class="col-destinationapp"> ##appName## </td></tr>`;
      let rowDataBuilder = "";

      /**
       * Iterate server list to create server row HTML
       */
      _.each(serverData, (server, index) => {
        var serverName = server.name;
        var destinationApp = server.content.destinationapp;
        var serverAppName = (destinationApp) ? destinationApp + ':' + serverName : 'Splunk_TA_jmx:' + serverName;
        var formatRow = serverDataRows.replace("##type##", this.rowType[index % 2]);

        // Display the alert icon and server edit dialog deep link url with server name if server account configuration is missing otherwise display server name.
        if (parseInt(server.content.has_account) === 1 && server.content.account_name === undefined) {

          var serverNameHTML = _.template(missingAccountAuthConfig, {
            title: StringUtil.escapeHTML(serverName),
			flag: 'account'
          });
          formatRow = formatRow.replace("##alertIcon##", serverNameHTML)
        } else {
          formatRow = formatRow.replace("##alertIcon##", '')
        }

        formatRow = formatRow.replace(/##name##/g, serverName);
        formatRow = formatRow.replace("##value##", serverAppName);
        formatRow = formatRow.replace("##description##", (server.content.description) ? server.content.description : '');
        formatRow = formatRow.replace("##appName##", (destinationApp) ? destinationApp : '');
        formatRow = formatRow.replace("##interval##", (server.content.interval) ? server.content.interval : '');

        if (this.serverArray.indexOf(serverAppName) >= 0) {
          formatRow = formatRow.replace("##checked##", "checked");
        } else {
          formatRow = formatRow.replace("##checked##", "");
        }
        rowDataBuilder = rowDataBuilder + formatRow;
      });
      $('.serversData').html(rowDataBuilder);

      /**
       * Server Tab click event
       */
      $("#servers-li").on("click", function () {
        $(".serverTab").show();
        $(".templatesTab").hide();
        $("#serversli").addClass("active");
        $("#templatesli").removeClass("active");
      });

      this.convertTableToDataTable('.serversDataTable', {
        "pagingType": "full_numbers",
        "oLanguage": {
          "sSearch": "",
          "sSearchPlaceholder": "Filter"
        },
        "columnDefs": [
          {
            "width": "7%",
            "targets": 0
          },
          {
            "targets": 0,
            "orderable": false
          }
        ],
        "order": []
      }, true);

    }

    /** For rendering template HTML
     * @class Hook
     * @method renderTemplateHtml
     * @params serverData - Server List
     */
    renderTemplateHtml(templateData) {

      var templateDataRows = `<tr class="apps-table-tablerow ##type##" ><td class="bs-checkbox "><input name="btSelectItem" type="checkbox" value="##value##" ##checked##></td><td class="col-name"><a class="external" href="` + this.accountConfigURL + `?tab=template&record=##name##" target="_blank">##name##</a></td><td class="col-description"> ##description## </td><td class="col-destinationapp"> ##appName## </td></tr>`;
      let rowDataBuilder = "";

      /**
       * Iterate template list to create template row HTML
       */
      _.each(templateData, (template, index) => {
        var destinationApp = template.content.destinationapp;
        var templateName = template.name;
        var templateAppName = (destinationApp) ? destinationApp + ':' + templateName : 'Splunk_TA_jmx:' + templateName;

        var formatRow = templateDataRows.replace(/##name##/g, templateName);
        formatRow = formatRow.replace("##type##", this.rowType[index % 2]);
        formatRow = formatRow.replace("##value##", templateAppName);
        formatRow = formatRow.replace("##description##", (template.content.description) ? template.content.description : '');
        formatRow = formatRow.replace("##appName##", (destinationApp) ? destinationApp : '');
        if (this.templateArray.indexOf(templateAppName) >= 0) {
          formatRow = formatRow.replace("##checked##", "checked");
        } else {
          formatRow = formatRow.replace("##checked##", "");
        }
        rowDataBuilder = rowDataBuilder + formatRow;
      });
      $('.templatesData').html(rowDataBuilder);

      /**
       * Template Tab click event
       */
      $("#templates-li").on("click", () => {
        $(".templatesTab").show();
        $(".serverTab").hide();
        $("#templatesli").addClass("active");
        $("#serversli").removeClass("active");
      });

      this.convertTableToDataTable('.templatesDataTable', {
        "bAutoWidth": false,
        "pagingType": "full_numbers",
        "oLanguage": {
          "sSearch": "",
          "sSearchPlaceholder": "Filter"
        },
        "columnDefs": [
          {
            "width": "7%",
            "targets": 0
          },
          {
            "targets": 0,
            "orderable": false
          }
        ],
        "order": []
      }, true);

    }

    /**
     * Convert normal table to Data table
     * @param {attribute} table id or class attribute value
     *   To pass id attribute, use hash (#) character, followed by the id value of the attribute
     *   To pass class attribute, use hash (.) character, followed by class id value of the attribute
     * @param {configuration} configuration
     *   Configuration object for the data table.
     * @param {isCheckBoxColumn} boolean
     *   Pass true if table checkbox column is available else pass false
     */
    convertTableToDataTable(attribute, configuration, isCheckBoxColumn = false) {

      if (!$.fn.dataTable.isDataTable(attribute)) {
        var table = $(attribute).DataTable(configuration).columns.adjust();
      }

      if (isCheckBoxColumn) {

        /**
         * Check each table body row checked or not.
         * Checked table header checkbox if all table body row checked else unchecked header checkbox
         */
        var dataTableBodyRowCheckboxChangeEvent = function () {

          let rows = table.rows({ 'filter': 'applied' }).nodes();
          let selectFlag = true;

          for (let i = 0; i < rows.length; i++) {
            if (!rows[i].cells[0].getElementsByTagName('input')[0].checked) {
              $(attribute + ' thead input[type=checkbox]').prop("checked", false);
              selectFlag = false;
              break;
            }
          }
          if (selectFlag) {
            $(attribute + ' thead input[type=checkbox]').prop("checked", true);
          }
        }

        /**
         * Table header checkbox change event
         */
        $(attribute).on("change", 'thead input[type=checkbox]', function () {
          var checked = this.checked;
          var rows = table.rows({ 'filter': 'applied' }).nodes();
          for (var i = 0; i < rows.length; i++) {
            rows[i].cells[0].getElementsByTagName('input')[0].checked = checked;
          }
        });

        /**
         * Table body row checkbox change event
         */
        $(attribute).on("change", 'tbody input[type=checkbox]', function () {
          dataTableBodyRowCheckboxChangeEvent();
        });

        /**
         * Update the table header checkbox when filter the data
         */
        $(attribute).parent().find('input[type=search]').on('keyup', function () {
          dataTableBodyRowCheckboxChangeEvent()
        });

        /**
         * Edit time update the table header checkbox
         */
        if (this.model.get('name')) {
          dataTableBodyRowCheckboxChangeEvent();
        }

      }

    }



    /** For rendering Tab HTML
     * @class Hook
     * @method renderTabs
     * @params data
     * @return String - Tab HTML
     */
    renderTabs(data) {

      return _.template(inputTab, data);
    }
  }
  return CustomInputTab;
});