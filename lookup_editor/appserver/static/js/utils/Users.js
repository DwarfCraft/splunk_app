/**
 * This helper will provide an easy way to get the list of users.
 */

require.config({
    paths: {
        console: '../app/lookup_editor/js/lib/console'
		
    }
});

define([
    'underscore',
    'backbone',
    'models/SplunkDBase',
    'collections/SplunkDsBase',
    'splunkjs/mvc',
    'util/splunkd_utils',
    'jquery',
    'console'
], function(
    _,
    Backbone,
    SplunkDBaseModel,
    SplunkDsBaseCollection,
    mvc,
    splunkd_utils,
    $
){

    var Users = {

        /**
         * Get a list of users.
		 * 
		 * @param owner The name of the owner of the lookup (so that the list can denote which of the users in the list is the owner)
         */
        getUsers: function(owner, descriptions, other_users){

        	// Get a promise ready
            var promise = jQuery.Deferred();
            
            // If this is the free license, then just return an empty array
            if ($C.SPLUNKD_FREE_LICENSE) {
                promise.resolve([]);
            }
            else {        	
                // Make the URL to get the list of users
                var uri = Splunk.util.make_url("/splunkd/__raw/services/admin/users?output_mode=json");

                // Let's do this
                jQuery.ajax({
                    url:     uri,
                    type:    'GET',
                    success: function(result) {
                        promise.resolve(this.makeUsersList(owner, result.entry, descriptions, other_users));
                    }.bind(this),
                    error: function() {
                        // This typlically happens when the user doesn't have access to the list of users (a non-admin account)
                        promise.resolve(this.makeUsersList(owner, null, descriptions, other_users));
                    }.bind(this)
                });

            }
        	
        	return promise;
        	
        },
        
        /**
         * Sort the list of users based alphabetically, but put the users in the priority list at
         * the top.
         */
        sortUsersList: function(users, users_to_prioritze){

            // Sort the list
            function compare(usera, userb) {

                var usera_name = usera.name.toLowerCase();
                var userb_name = userb.name.toLowerCase();

                // Give priority to the users in the priority list
                for (var c = 0; c < users_to_prioritze.length; c++) {
                    if (usera.name == users_to_prioritze[c]) {
                        return -1;
                    }

                    if (userb.name == users_to_prioritze[c]) {
                        return 1;
                    }
                }

                // Otherwise, sort them alphabectically
                if (usera_name < userb_name) {
                    return -1;
                }
                if (usera_name > userb_name) {
                    return 1;
                }
                // usera must be equal to userb
                return 0;
            }

            users.sort(compare);

            return users;
        },

        /**
         * Create a list of users for the lookup context dialog
		 * 
		 * @param owner The name of the owner of the lookup (so that the list can denote which of the users in the list is the owner)
		 * @param users_list_from_splunk The list of users as enumerated from Splunk
         * @param descriptions An associative array of descriptions
         * @param other_users An array of other entries to add to the list
         */
        makeUsersList: function(owner, users_list_from_splunk, descriptions, other_users){
        	
        	// Set a default value for version
        	if(typeof users_list_from_splunk == 'undefined'){
        		users_list_from_splunk = [];
        	}
        	
        	// Make a list of users to show from which to load the context
        	var users = [];
        	var user = null;
            var description = '';

        	for(var c = 0; c < users_list_from_splunk.length; c++){
        		user = users_list_from_splunk[c];
                
                // Get the description from the user name if necessary
                if(descriptions && descriptions[user.name]){
                    description = descriptions[user.name];
                }
                else{
                    description = '';
                }
        		
        		// Add the user
				users.push({
					'name' : user.name,
					'readable_name' : user.content.realname.length > 0 ? user.content.realname : user.name,
					'description' : description
				});
        	}
        	
        	// If we didn't get users, then populate it manually
            for(var c = 0; other_users && c < other_users.length; c++){
                users.push(other_users[c]);
            }
        	
			// Uniqify the list
        	users = _.uniq(users, function(item, key, a) { 
        	    return item.name;
        	});

			return users;
        }
    };

    return Users;
});
