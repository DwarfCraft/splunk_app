/**
 * This component shows a modal that is used for performing imports.
 */

require.config({
    paths: {
        console: '../app/lookup_editor/js/lib/console',
        text: '../app/lookup_editor/js/lib/text'
    }
});

define([
    'underscore',
    'backbone',
    'models/SplunkDBase',
    'collections/SplunkDsBase',
    'splunkjs/mvc',
    'splunkjs/mvc/simplesplunkview',
    'util/splunkd_utils',
    'jquery',
    'text!../app/lookup_editor/js/templates/ImportModal.html',
    'css!../app/lookup_editor/css/ImportModal.css',
    'console'
], function(
    _,
    Backbone,
    SplunkDBaseModel,
    SplunkDsBaseCollection,
    mvc,
    SimpleSplunkView,
    splunkd_utils,
    $,
    Template
){

    // Define the custom view class
    var ImportModal = SimpleSplunkView.extend({
        className: "ImportModal",
            
        defaults: {
                
        },
            
        /**
         * Initialize the class.
         */
        initialize: function() {
            this.options = _.extend({}, this.defaults, this.options);

            this.cancel_import= false;
        },

        events: {
        	"click #choose-import-file"                    : "chooseImportFile",
        	"click #import-file"                           : "openFileImportModal",
        	"change #import-file-input"                    : "importFile",
			"click #import-file-modal .btn-dialog-cancel"  : "cancelImport",
			"click #import-file-modal .btn-dialog-close"   : "cancelImport",
        },

        /**
         * Open the file dialog to select a file to import.
         */
        chooseImportFile: function(){
        	$("#import-file-input").click();
        },

        /**
         * Open the modal for importing a file.
         */
        openFileImportModal: function(){
        	
        	$('.dragging').removeClass('dragging');
        	
			// Make sure we are showing the import dialog
			$('#import-in-process', this.$el).hide();
			$('#import-main', this.$el).show();

			// Open the modal
        	$('#import-file-modal', this.$el).modal();
        	
        	// Setup handlers for drag & drop
        	$('.modal-backdrop', this.$el).on('dragenter', function(){
        		$('.modal-body').addClass('dragging');
        	});
        	
        	$('.modal-backdrop', this.$el).on('dragleave', function(){
        		$('.modal-body').removeClass('dragging');
        	});
        	
        	$('#import-file-modal', this.$el).on('dragenter', function(){
        		$('.modal-body').addClass('dragging');
        	});
        },

        /**
         * For some reason the backbone handlers don't work.
         */
        setupDragDropHandlers: function(){

        	// Setup a handler for handling files dropped on the import dialog
        	drop_zone = document.getElementById('import-file-modal');
        	this.setupDragDropHandlerOnElement(drop_zone);
        	
        },
        
		/**
		 * Setup a drag and handler on an element.
		 * 
		 * @param drop_zone An element to setup a drop-zone on.
		 */
        setupDragDropHandlerOnElement: function(drop_zone){
			
			if(drop_zone){
				drop_zone.ondragover = function (e) {
					e.preventDefault();
					e.dataTransfer.dropEffect = 'copy';
				}.bind(this);
				
				drop_zone.ondrop = function (e) {
					e.preventDefault();
					this.onDropFile(e);
					return false;
				}.bind(this);
			}
        },
        
		/**
		 * The handler for file-dragging.
		 * 
		 * @param evt The event
		 */
        onDragFile: function(evt){
        	evt.stopPropagation();
            evt.preventDefault();
            evt.dataTransfer.dropEffect = 'copy'; // Make it clear this is a copy
        },
        
        /**
         * Import the dropped file.
		 * 
		 * @param evt The event associated with the call
         */
        onDropFile: function(evt){
        	
        	console.log("Got a file via drag and drop");
        	evt.stopPropagation();
            evt.preventDefault();
            
            this.importFile(evt);
        },

        /**
         * Tell the caller to import the file
         * 
         * @param evt The event associated with the call
         */
        importFile: function(evt){
            this.trigger('startImport', evt);
        },

        /* 
         * Cancel an import that is in-progress.
         */
        cancelImport: function () {
            this.cancel_import = true;
            this.trigger("cancelImport");
        },

        /**
         * Change the dialog to show the progress of an importation job.
         * 
         * @param total The total number of entries to be imported
         * @param successes The total number of entries already imported
         * @param errors The total entries that couldn't be imported
         */
        setProgress: function(total, successes, errors){
			$('#import-in-process', this.$el).show();
			$('#import-main', this.$el).hide();
			$('#import-file-modal .modal-body', this.$el).removeClass("dragging");

			$('#import-progress', this.$el).css('width', 100*(successes/total) + "%");
			$('#import-error', this.$el).css('width', 100*(errors/total) + "%");
        },

        /**
         * Show the modal with options appropriate for the given lookup type.
         * 
         * @param lookup_type The type of lookup (either "kv" or "csv")
         */
        show: function(lookup_type){

            // No need to do anything if the dialog is already open
            if($('#import-file-modal:visible', this.$el).length > 0){
                return;
            }

            this.lookup_type = lookup_type;
            this.render();

			// Open the import modal
			this.openFileImportModal();
        },

        /**
         * Close the modal.
         */
        hide: function(){
            $('#import-file-modal', this.$el).modal('hide');
        },

        /**
         * Render the HTML for the dialog.
         */
        render: function(){
            this.$el.html(_.template(Template, {
                'lookup_type' : this.lookup_type
            }));

            this.setupDragDropHandlers();

            console.log("Rendering the import modal");
        }
    });

    return ImportModal;
});