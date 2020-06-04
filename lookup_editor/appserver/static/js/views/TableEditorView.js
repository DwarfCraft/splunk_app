/**
 * This view provides a wrapper around Handontable for the use of displaying and modifying the
 * contents of lookup files.
 * 
 * This class exposes a series of Backbone events that can be used to listen for actions. Below is
 * the list:
 * 
 *    1) editCell: when a cell gets edited
 *    2) removeRow: when a row gets removed
 *    3) createRows: when a series of new rows are to be created
 */
require.config({
    paths: {
		jexcel: '../app/lookup_editor/js/lib/jexcel/jexcel',
		jsuites: '../app/lookup_editor/js/lib/jsuites/jsuites',
		formatTime: '../app/lookup_editor/js/utils/FormatTime',
		"console": '../app/lookup_editor/js/lib/console',
		"bootstrap-tags-input": "../app/lookup_editor/js/lib/bootstrap-tagsinput.min",
		contextMenu: '../app/lookup_editor/js/utils/ContextMenu'
    },
    shim: {
        'bootstrap-tags-input': {
        	deps: ['jquery']
		},
        'jexcel': {
        	deps: ['jquery', 'jsuites']
		},
    }
});

define([
    "underscore",
    "backbone",
	"jquery",
	"splunkjs/mvc/simplesplunkview",
	"formatTime",
	"contextMenu",
	"jexcel",
	"jsuites",
	"bootstrap-tags-input",
    "splunk.util",
	"css!../app/lookup_editor/js/lib/bootstrap-tagsinput.css",
	"css!../app/lookup_editor/css/TagsInput.css",
	"css!../app/lookup_editor/js/lib/jexcel/jexcel.css",
	"css!../app/lookup_editor/js/lib/jsuites/jsuites.css",
	"css!../app/lookup_editor/css/TableEditorView.css",
], function(
    _,
    Backbone,
    $,
	SimpleSplunkView,
	formatTime,
	contextMenu,
){

    // Define the custom view class
    var TableEditorView = SimpleSplunkView.extend({
        className: "TableEditorView",
        
        /**
         * Initialize the class.
         */
        initialize: function() {
        	this.options = _.extend({}, this.defaults, this.options);
            
            // Here are the options:
            this.lookup_type = this.options.lookup_type; // The type of lookup (csv or kv)

            // Below is the list of internal variables
            this.jexcel = null; // A reference to the handsontable

            this.field_types = {}; // This will store the expected types for each field
            this.field_types_enforced = false; // This will store whether this lookup enforces types
            this.read_only = false; // We will update this to true if the lookup cannot be edited
            this.table_header = null; // This will store the header of the table so that can recall the relative offset of the fields in the table

            // These are copies of editor classes used with the handsontable
			this.default_editor = null;
        },

        /**
         * Get the field name for the column.
		 * 
		 * @param col The column to get the table header information from.
         */
        getFieldForColumn: function(col){
        	var row_header = this.getTableHeader();
        	return row_header[col];
        },

        /**
         * Validate that the lookup contents are a valid file
         * 
         * @param data The data (array of array) representing the table
         * @returns {Boolean}
         */
        validate: function(data) {
        	// If the cell is the first row, then ensure that the new value is not blank
        	if( data[0][0] === 0 && data[0][3].length === 0 ){
        		return false;
        	}
        },

        /**
         * Cell renderer for HandsOnTable. This function converts the values and applies styling so that users see readable data.
		 * 
		 * @param instance The instance of the Handsontable
		 * @param td The TD element
		 * @param row The row number
		 * @param col The column number
		 * @param value The value of the cell
		 * @param value2 The value of the cell
		 * @param cellProperties
         */
        lookupRenderer: function(instance, td, row, col, value, value2, cellProperties) {
			// Convert KV store time fields
			if(this.lookup_type === 'kv' && this.getFieldTypeByColumn(col) === "time") {
				td.innerHTML = formatTime(value, true);
				return;
			}

			// Convert KV store array fields
			if(this.lookup_type === 'kv' && this.getFieldTypeByColumn(col) === "array") {
				return this.arrayRenderer(instance, td, row, col, value, value2, cellProperties);
			}

			// Otherwise don't mess with the other KV store fields, it tends to break things
			else if(this.lookup_type === 'kv' && this.getFieldTypeByColumn(col) !== "text") {
				return;
			}

        	// Don't render a null value
        	if(value === null){
        		td.innerHTML = this.escapeHtml("");
        	}
        	else{
        		td.innerHTML = this.escapeHtml(value);
        	}
        	
        	// Determine if the value is a string so that we can know if we can perform string-related operations on it later
        	var is_a_string = false;
        	
        	if(value){
        		is_a_string = (typeof value.toLowerCase === 'function');
        	}
        	
        	// Execute the renderer
        	if(this.isCellTypeInvalid(row, col, value)) { // Cell type is incorrect
        		td.className = 'cellInvalidType';
			}
			// Convert CSV _time fields
			else if(this.getFieldForColumn(col) === "_time") { // Cell type is _time
				td.innerHTML = formatTime(value, false);
			}
        	else if(!value || value === '') {
        		td.className = 'cellEmpty';
        	}
        	else if(this.getFieldForColumn(col) === "_key"){
        		td.className = 'cellKey';
        	}
        	else if (parseFloat(value) < 0) { //if row contains negative number
        		td.className = 'cellNegative';
        	}
        	else if( String(value).substring(0, 7) == "http://" || String(value).substring(0, 8) == "https://"){
        		td.className = 'cellHREF';
        	}
        	else if (parseFloat(value) > 0) { //if row contains positive number
        		td.className = 'cellPositive';
        	}
        	else if(value !== null && is_a_string && value.toLowerCase() === 'true') {
        		td.className = 'cellTrue';
        	}
        	else if(value !== null && is_a_string && value.toLowerCase() ==='false') {
        		td.className = 'cellFalse';
        	}
        	else if(value !== null && is_a_string && value.toLowerCase() === 'unknown') {
        		td.className = 'cellUrgencyUnknown';
        	}
        	else if(value !== null && is_a_string && value.toLowerCase() === 'informational') {
        		td.className = 'cellUrgencyInformational';
        	}
        	else if(value !== null && is_a_string && value.toLowerCase() === 'low') {
        		td.className = 'cellUrgencyLow';
        	}
        	else if(value !== null && is_a_string && value.toLowerCase() === 'medium') {
        		td.className = 'cellUrgencyMedium';
        	}
        	else if(value !== null && is_a_string && value.toLowerCase() === 'high') {
        		td.className = 'cellUrgencyHigh';
        	}
        	else if(value !== null && is_a_string && value.toLowerCase() === 'critical') {
        		td.className = 'cellUrgencyCritical';
        	}
        	else {
        		td.className = '';
        	}
        	
        	if(cellProperties && cellProperties.readOnly) {
        	    td.style.opacity = 0.7;
        	}
        },
		
		/**
		 * Convert a value to the format it needs to be in order to be saved.
		 * @param {*} value 
		 */
		convertTimeValue: function(value){

			// Try to convert the value to the epoch time
			var converted_value = new Date(value).valueOf();

			// If we couldn't convert it, then pass it through (see https://lukemurphey.net/issues/2262)
			if(!isNaN(converted_value)){
				return String(converted_value);
			}

			return value;
		},

        /**
         * Get the data from the table.
         * 
         * This is largely just a pass-through to HandsOnTable with the exception of for lookups
		 * with a _time field. In that case, the time value will be converted from a string to an
		 * integer.
         */
        getData: function(){
			var data = this.jexcel.getData();

			var convert_columns = {};

			// Figure out if any columns must be converted from _time
			var row_header = this.getTableHeader();

			for(var c = 0; c < row_header.length; c++){
        		if(row_header[c] === '_time'){
					convert_columns[c] = this.convertTimeValue;
        		}
			}
			
			// Figure out if any columns must be converted into arrays
			var array_columns = [];

			for(var c = 0; c < row_header.length; c++){
				var field_type = this.getFieldType(c);
        		if(field_type === 'array'){
        			array_columns.push(c);
        		}
        	}

			// Return the current data if there are no times or arrays that need to be converted
			var convert_columns_count = 0;
			for (var k in convert_columns) {
				if (convert_columns.hasOwnProperty(k)) {
				   ++convert_columns_count;
				}
			}

			// No columns need conversion, just return the data
			if(convert_columns_count === 0){
				return data;
			}

			// Process each row
			for(c = 0; c < data.length; c++){
				for(column = 0; column < data[c].length; column++){
					if(column in convert_columns){
						data[c][column] = convert_columns[column](data[c][column]);
					}
				}
			}

			return data;
        },

        /**
         * Get the data from the table for the given row.
         * 
         * Note: this is just a pass-through to HandsOnTable
         * 
         * @param row An integer designating the row
         */
        getDataAtRow: function(row){
			// jexcel works using cells that are off by one from the way that HandsOnTable worked
			var rowUpdated = parseInt(row) - 1;
            return this.jexcel.getRowData(rowUpdated);
        },

        /**
         * Get the data from the table for the given row.
         * 
         * Note: this is just a pass-through to HandsOnTable
         * 
         * @param row An integer designating the row
         * @param column The column number to edit or a string value of the column name
         * @param value The value to set to
         * @param operation A string describing the value
         */
        setDataAtCell: function(row, column, value, operation){
            // If the column is a string, then this is a column name. Resolve the actual column
			// name.
            if(typeof column === "string"){
                column = this.getColumnForField(column);
			}
			
			// jexcel works using cells that are off by one from the way that HandsOnTable worked
			var row = parseInt(row) - 1;
			this.jexcel.setValueFromCoords(column, row, value, true);
        },

        /**
         * Get the table header.
		 * 
		 * @param use_cached Use the cached version of the table-header.
         */
        getTableHeader: function(use_cached){
        	
        	// Assign a default argument to use_cached
        	if(typeof use_cached === 'undefined'){
        		use_cached = true;
        	}
        	
        	// Use the cache if available
        	if(use_cached && this.table_header !== null){
        		return this.table_header;
        	}
			
			this.table_header = this.jexcel.getHeaders(true);
        	
        	return this.table_header;
        },
        
        /**
         * Get the column that has a given field name.
		 * 
		 * @param field_name The name of the field to get the header for
         */
        getColumnForField: function(field_name){
        	
        	var row_header = this.getTableHeader();

        	for(var c = 0; c < row_header.length; c++){
        		if(row_header[c] === field_name){
        			return c;
        		}
        	}
        	
        	console.warn('Unable to find the field with the name "' + field_name + '"');
        	return null;
        },

        /**
         * Determine if the cell type is invalid for KV cells that have enforced data-types.
		 * 
		 * @param row The row number of the cell to be validated
		 * @param col The column number of the cell to be validated
		 * @param value The value to validate
         */
        isCellTypeInvalid: function(row, col, value){
        	
        	// Stop if type enforcement is off
        	if(!this.field_types_enforced){
        		return false;
        	}
        	
        	// Determine the type of the field
        	var field_type = this.getFieldType(col);
        	
        	// Check it if it is an number
        	if(field_type === 'number' && !/^[-]?\d+(.\d+)?$/.test(value)){
    			return true;
    		}
    		
    		// Check it if it is an boolean
    		else if(field_type === 'boolean' && !/^(true)|(false)$/.test(value)){
    			return true;
			}
			
    		// Check it if it is an CIDR
    		else if(field_type === 'cidr' && !/^([0-9]{1,3}\.){3}[0-9]{1,3}(\/([0-9]|[1-2][0-9]|3[0-2]))?$/igm.test(value)){
    			return true;
    		}
        	
        	return false;
        },

        /**
         * Get the type associated with the given field.
		 * 
		 * @param column The name of the field to get the type of
         */
        getFieldType: function(column){
        	
        	// Stop if we didn't get the types necessary
        	if(!this.field_types){
        		return null;
        	}
        	
        	var table_header = this.getTableHeader();
        	
        	// Stop if we didn't get the header
        	if(!table_header){
        		return null;
        	}
        	
        	if(column < this.table_header.length){
        		return this.field_types[table_header[column]];
        	}
        	
        	// Return null if we didn't find the entry
        	return null;
        	
        },

        /**
         * Get column configuration data for the columns from a KV store collection so that the table presents a UI for editing the cells appropriately. 
		 * 
		 * This function is for getting the columns meta-data for KV store lookup editing; it won't work for CSV lookups since
		 * they don't have field_types nor an _key field.
         */
        getColumnsMetadata: function(){
        	
        	// Stop if we don't have the required data yet
        	if(!this.getTableHeader()){
        		console.warn("The table header is not available yet");
        	}

        	var table_header = this.getTableHeader();
        	var column = null;
        	var columns = []; 
        	
        	// Stop if we didn't get the types necessary
        	if(!this.field_types){
        		console.warn("The table field types are not available yet");
        	}
        	
        	// This variable will contain the meta-data about the columns
        	// Columns are going to have a single field by default for the _key field which is not included in the field-types
        	var field_info = null;
        	
        	for(var c = 0; c < table_header.length; c++){
				var header_column = table_header[c];
				field_info = this.field_types[header_column];
				
        		column = {
					'title': header_column,
					'readOnly': this.read_only || (this.lookup_type === 'kv' && header_column === '_key'),
				};
        		
        		// Use a checkbox for the boolean
        		if(field_info === 'boolean'){
        			column.type = 'checkbox';
        		}
        		
        		// Use format.js for the time fields
        		else if(field_info === 'time'){
					/*
					column.type = 'calendar';
					column.options = {
						format:'YYYY/MM/DD HH:MM:SS',
						time: 1,
						placeholder:'YYYY/MM/DD HH:mm:ss',
					};
					*/
					column.editor = this.getTimeColumn();
				}
				
        		// Use the tags input for the array fields
        		else if(field_info === 'array'){
					column.editor = this.getArrayColumn();
        		}
        		
        		// Handle number fields
        		else if(field_info === 'number'){
					column.type = 'numeric';
					column.decimal = '.',
					column.mask = '[-]#.0000000000000000'
				}
				
				// Put in a default column editor if necessary
				else {
					column.editor = this.getEscapedHtmlColumn();
				}
        		
        		columns.push(column);
    		}
    		
        	return columns;
        },

        /**
         * Re-render the Hands-on-table instance
         */
        reRenderHandsOnTable: function(){
        	
        	// Re-render the view
        	if(this.$el.length > 0 && this.jexcel){
            	if(this.jexcel){
            		this.jexcel.render(); // TODO check
            	}
        	}
        },
		
        /**
         * Render array content (as a set of labels)
		 * 
		 * @param instance The instance of the Handsontable
		 * @param td The TD element
		 * @param row The row number
		 * @param col The column number
		 * @param prop
		 * @param value The value of the cell
		 * @param cellProperties
         */
		arrayRenderer: function(instance, td, row, col, prop, value, cellProperties) {
			// Stop if the content is empty
			if(prop === null || prop.length === 0){
				td.innerHTML = "";
			}

			// Try to parse the content
			else {
				try {
					// By default assume the incoming value is a list
					var values = prop;

					// If this is a string, then parse it
					if(typeof prop === "string"){
						values = JSON.parse(prop);
					}

					// Make the HTML
					var labels_template = _.template('<% for(var c = 0; c < values.length; c++){ %><span class="label label-default label-readonly arrayValue"><%- values[c] %></span><% } %>');

					td.innerHTML = labels_template({ values: values});
				}
				catch(err) {
					console.warn("Unable to parse the cell values:" + prop);
					td.innerHTML = prop;
				}
			}

            return td;
		},

        /**
         * Escape HTML content
		 * 
		 * @param instance The instance of the Handsontable
		 * @param td The TD element
		 * @param row The row number
		 * @param col The column number
		 * @param prop
		 * @param value The value of the cell
		 * @param cellProperties
         */
        escapeHtmlRenderer: function(instance, td, row, col, prop, value, cellProperties) {
        	td.innerHTML = this.escapeHtml(Handsontable.helper.stringify(value));

            return td;
		},
		
		/**
		 * Below is the list of column renderers
		 */
		getDefaultColumn: function() {
			return {
				closeEditor : function(cell, save) {
					var value = cell.children[0].value;
					cell.innerHTML = value;
					return value;
				},
				openEditor : function(cell) {
					// Create input
					var element = document.createElement('input');
					element.value = cell.innerHTML;

					// Update cell
					cell.classList.add('editor');
					cell.innerHTML = '';
					cell.appendChild(element);

					// Focus on the element
					element.focus();
				},
				getValue : function(cell) {
					return cell.innerHTML;
				},
				setValue : function(cell, value) {
					cell.innerHTML = value;
				}
			};
		},

		getEscapedHtmlColumn: function() {
			var defaultColumn = this.getDefaultColumn();

			defaultColumn.setValue = function(cell, value) {
				cell.innerHTML = this.escapeHtml(value);
			}.bind(this);

			defaultColumn.getValue = function(cell) {
				return this.escapeHtml(cell.innerHTML);
			}.bind(this);

			return defaultColumn;
		},

		getTimeColumn: function() {
			var defaultColumn = this.getDefaultColumn();
			placeholder:'YYYY/MM/DD HH:mm:ss',

			defaultColumn.openEditor = function(cell) {
				// Create input
				var element = document.createElement('input');
				element.value = cell.innerHTML;
				element.setAttribute('placeholder', 'YYYY/MM/DD HH:mm:ss');

				// Update cell
				cell.classList.add('editor');
				cell.innerHTML = '';
				cell.appendChild(element);

				// Focus on the element
				element.focus();
			},

			defaultColumn.setValue = function(cell, value) {
				cell.innerHTML = formatTime(value, this.lookup_type === "kv");
			}.bind(this);

			return defaultColumn;
		},

		getArrayColumn: function() {
			return {
				closeEditor : function(cell, save) {
					// var value = $(cell.children[1]).tagsinput('items').join(',');
					var values = $(cell.children[1]).tagsinput('items');
					cell.innerHTML = values;
					return values;
				}.bind(this),
				openEditor : function(cell) {
					// Get the value of the cell in array format
					var values = this.getValue(cell);

					// Create textarea
					var element = document.createElement('textarea');

					// Hide the existing value
					cell.innerHTML = '';

					cell.appendChild(element);
					$(element).attr("placeholder", "Enter values separated by commas; click outside the cell to persist the value");

					// Create the tags input widget
					$(element).tagsinput({
						confirmKeys: [44],
						allowDuplicates: true,
						tagClass: 'label label-info arrayValue'
					});

					$(element).tagsinput('removeAll');
	
					try {
						for(var c=0; c < values.length;c++){
							$(element).tagsinput('add', values[c]);
						}
					}
					catch(err) {
						// The value could not be parsed
						console.warn("Unable to parse the values: ", values);
					}

					// Focus on the element
					element.focus();
				},
				getValue : function(cell) {
					var values = $('.arrayValue', cell);
					var parsed = [];

					for(var c=0; c < values.length;c++){
						parsed.push(values[c].innerHTML);
					}
					return parsed;
				},
				setValue : function(cell, value) {
					cell.innerHTML = JSON.stringify(value);
				}.bind(this)
			};
		},

        /**
         * Add some empty rows to the lookup data.
		 * 
		 * @param data An array of rows that the empty cells will be added to
		 * @param column_count The number of columns to add
		 * @param row_count The number of rows to add
         */
        addEmptyRows: function(data, column_count, row_count){
        	var row =[];
        	
        	for(var c = 0; c < column_count; c++){
        		row.push('');
        	}
        	
        	for(c = 0; c < row_count; c++){
        		data.push($.extend(true, [], row));
        	}
        	
		},
		
		/**
		 * Search the lookup for the given data
		 *
		 * @param text the text to search for 
		 */
		search: function(text){
			this.jexcel.search(text);
		},

        /**
         * Render the lookup.
		 * 
		 * @param data The array of arrays that represents the data to render
         */
        renderLookup: function(data){			
        	if(data === null){
        		console.warn("Lookup could not be loaded");
        		return false;
        	}

        	// Store the table header so that we can determine the relative offsets of the fields
        	this.table_header = data[0];
        	
        	// Put in a class name so that the styling can be done by the type of the lookup
        	if(this.lookup_type === "kv"){
        		this.$el.addClass('kv-lookup');
        	}

			// I need to set the column width 
			var width = $(this.$el[0]).width() - 80;
			var column_count = data[0].length;
			var column_width = width / column_count;
			var overflow = false;

			if(column_width < 100){
				column_width = 100;
				overflow = true;
			}

			// Figure out the height
			var computed_height = $(window).height() - $(this.$el[0]).offset().top - 100;

			// Make the columns
			var columns = this.getColumnsMetadata();
			
			// Remove the header
			data.splice(0, 1);

			// Make the base options list
			var options = {
				data: data,
				defaultColWidth: column_width,
				tableOverflow: true,
				loadingSpin: true,
				columns: columns,
				lazyLoading: true,
				allowExport: false,
				contextMenu: contextMenu.bind(this),
				editable: !this.read_only,
				defaultColAlign: 'left',
				tableWidth: width,
				tableHeight: computed_height + 'px',
				minSpareRows: data.length === 0 ? 1 : 0,
				updateTable: function(el, cell, col, row, data, text, column_name) {
					this.lookupRenderer(el, cell, row, col, data, text);
				}.bind(this)
			}

            // Wire-up handlers for doing KV store dynamic updates
            if(this.lookup_type === "kv"){
				options.onchange = function(instance, cell, x, y, value) {
					this.trigger("editCell", {
						'row' : parseInt(y) + 1,
						'col' : parseInt(x) + 1,
						'new_value' : value
					});
				}.bind(this);
				
				options.onbeforedeleterow = function(instance, rowNumber, amount) {

					// Iterate and remove each row
                    for(var c = 0; c < amount; c++){
						var row = rowNumber + c + 1;
                        if(!this.trigger("removeRow", row)){
							return false;
						}
					}

					return true;
				}.bind(this);
				
				options.oninsertrow = function(instance, row, count, rowRecords, insertBefore) {
                    this.trigger("createRows", {
                        'row' : row,
                        'count' : count
					});
				}.bind(this);
			}

			// Load the editor
			if(this.jexcel){
				this.jexcel.setData(data);
				var editor = this.jexcel;
				this.table_header.forEach(function(header_column, index) {
					editor.setHeader(index, header_column);
				});
			}
			else {
				var computed_height = ($(window).height() - $(this.$el[0]).offset().top - 100);
				this.jexcel = $(this.$el[0]).jexcel(options);
			}
            
            // Return true indicating that the load worked
            return true;
        },

		/**
		 * Set the status to read-only
		 * 
		 * @param read_only A boolean indicating if the table should be in read-only mode.
		 */
		setReadOnly: function(read_only){
			this.read_only = read_only;
		},

		/**
		 * Determine if the table is in read-only mode.
		 */
		isReadOnly: function(){
			return this.read_only;
		},

		/**
		 * Set the field types and whether the types ought to be enforced.
		 * 
		 * @param field_types A list of the field types
		 */
		setFieldTypes: function(field_types){
			this.field_types = field_types;
		},

		/**
		 * Get the field types.
		 */
		getFieldTypes: function(){
			return this.field_types;
		},

		/**
		 * Get the field type for the name.
		 */
		getFieldType: function(name){
			return this.field_types[name];
		},

		/**
		 * Get the field type for the column.
		 */
		getFieldTypeByColumn: function(col){
			return this.field_types[this.getFieldForColumn(col)];
		},

		/**
		 * Set the field type enforcement to on.
		 * 
		 * @param field_types_enforced A boolean indicating whether the types should be enforced
		 */
		setFieldTypeEnforcement: function(field_types_enforced){
			this.field_types_enforced = field_types_enforced;
		},

		/**
		 * Get a boolean indicating whether field types are enforced.
		 */
		areFieldTypesEnforced: function(){
			return this.field_types_enforced;
		},

        /**
         * Make JSON for the given row.
		 * 
		 * @param row The number to convert
         */
        makeRowJSON: function(row){
        	// We need to get the row meta-data and the 
        	var row_header = this.getTableHeader();
        	var row_data = this.getDataAtRow(row);
        	
        	// This is going to hold the data for the row
        	var json_data = {};
        	
        	// Add each field / column
        	for(var c=1; c < row_header.length; c++){
        		
        		// Determine the column type if we can
        		var column_type = this.getFieldType(c);
        		
        		// This will store the transformed value (by default, it is the original)
        		var value = row_data[c];
        		
        		// If this is a datetime, then convert it to epoch integer
        		if(column_type === "time"){
					
					// See if the value is a number already and don't bother converting it if so
					if(/^[-]?\d+(.\d+)?$/.test(value)){
						// No need to convert it
					}
					else {
						value = new Date(value).valueOf();
					}
				}
				
        		// If this is a array, then convert it to an array
        		if(column_type === "array"){
					if(value.length == 0){
						value = "";
					}
					else{
						try {
							value = JSON.parse(value);
						}
						catch(err) {
						  throw "The value for the array is a not a valid array";
						}
					}
        		}
        		
        		// Don't allow undefined through
        		if(value === undefined){
        			value = '';
        		}
        		
        		this.addFieldToJSON(json_data, row_header[c], value);
        	}
        	
        	// Return the created JSON
        	return json_data;
        },

        /**
         * Add the given field to the data with the appropriate hierarchy.
		 * 
		 * @param json_data The JSON object to add the information to
		 * @param field The name of the field
		 * @param value The value to set
         */
        addFieldToJSON: function(json_data, field, value){
        	
        	var split_field = [];
        	
        	split_field = field.split(".");
        	
    		// If the field has a period, then this is hierarchical field
    		// For these, we need to build the heirarchy or make sure it exists.
    		if(split_field.length > 1){
    			
    			// If the top-most field doesn't exist, create it
    			if(!(split_field[0] in json_data)){
    				json_data[split_field[0]] = {};
    			}
    			
    			// Recurse to add the children
    			return this.addFieldToJSON(json_data[split_field[0]], split_field.slice(1).join("."), value);
    		}
    		
    		// For non-hierarchical fields, we can just add them
    		else{
    			json_data[field] = value;
    			
    			// This is the base case
    			return json_data;
    		}	
        },

	     /** 
	      * Use the browser's built-in functionality to quickly and safely escape a string of HTML.
		  * 
		  * @param str The string to escape
	      */
          escapeHtml: function(str) {
            var div = document.createElement('div');
            div.appendChild(document.createTextNode(str));
            return div.innerHTML;
        },
    });

    return TableEditorView;
});