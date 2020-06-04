define([
    "underscore",
    "backbone",
    "splunkjs/mvc",
    "util/splunkd_utils",
    "jquery",
    "splunkjs/mvc/simplesplunkview",
    "splunk.util"
], function(
    _,
    Backbone,
    mvc,
    splunkd_utils,
    $,
    SimpleSplunkView
){
	var Backup = Backbone.Model.extend();
	
	var Backups = Backbone.Collection.extend({
	    url: Splunk.util.make_full_url("/splunkd/__raw/services/data/lookup_edit/lookup_backups"),
	    model: Backup
	});
	
    // Define the custom view class
    var BackupListInput = SimpleSplunkView.extend({
        className: "BackupListInput",

        tagName: "span",

        events: {
        	"click .backup-version" : "doLoadBackup"
        },

        /**
         * Initialize the class.
         */
        initialize: function() {
            this.options = _.extend({}, this.defaults, this.options);
        	this.backups = null;
        },

        /**
         * Load the list of backup lookup files.
         * 
         * @param lookup_file The name of the lookup file
         * @param namespace The app where the lookup file exists
         * @param user The user that owns the file (in the case of user-based lookups)
         */
        loadLookupBackupsList: function(lookup_file, namespace, user){
        	var data = {
				"lookup_file":lookup_file,
				"namespace":namespace
			};
        	
        	// Populate the default parameter in case user wasn't provided
        	if( typeof user === 'undefined' ){
        		user = null;
        	}

        	// If a user was defined, then pass the name as a parameter
        	if(user !== null){
        		data.owner = user;
        	}
        	
        	// Fetch them
        	this.backups = new Backups();
        	this.backups.fetch({
        		data: $.param(data),
        		success: this.renderBackupsList.bind(this)
        	});
        },

        /**
         * Load the selected backup.
		 * 
		 * @param evt The event object
         */
        doLoadBackup: function(evt){
        	var version = evt.currentTarget.dataset.backupTime;
        	
        	if(version){
        		this.loadBackupFile(version);
        	}
        },

        /**
         * Load the selected lookup from the history.
         * 
         * @param version The version of the lookup file to load (a value of null will load the latest version)
         */
        loadBackupFile: function(version){
        	// Load a default for the version
        	if( typeof version == 'undefined' ){
        		version = null;
        	}
        	
        	var r = confirm('This version the lookup file will now be loaded.\n\nUnsaved changes will be overridden.');
        	
        	if (r === true) {
                this.trigger('loadBackup', version);
        		return true;
        	}
        	else{
        		return false;
        	}
        },

        /**
         * Render the list of backups.
         */
        renderBackupsList: function(){
            this.render();
        },

        /**
         * Render the list of backup files.
         */
        render: function(){
            // Set the content for the dropdown
            var template = '<a class="btn dropdown-toggle right-offset-button" data-toggle="dropdown" href="#">' +
                '   Revert to previous version' +
                '   <span class="caret"></span>' +
                '</a>' + 
                '<ul id="backup-versions" class="dropdown-menu">' +
                '<% for(var c = 0; c < backups.length; c++){ %> ' +
                '	<li><a class="backup-version" href="#" data-backup-time="<%- backups[c].time %>"><%- backups[c].time_readable %></a></li> ' +
                '<% } %> ' +
                '<% if(backups.length == 0){ %> ' +
                '	<li><a class="backup-version" href="#">No backup versions available</a></li> ' +
                '<% } %>' +
                '</ul>';

            // Render the list of backups
            $(this.$el).html(_.template(template, {
                'backups' : this.backups ? this.backups.toJSON() : []
            }));
        	
            // Show the list of backup lookups
            /*
        	if(!this.table_editor_view.isReadOnly()){
        		$('#load-backup', this.$el).show();
        	}
        	else{
        		$('#load-backup', this.$el).hide();
        	}
        	*/
        }
    });

    return BackupListInput;
});
