/**
 * This helper will provide an easy way to get the list of capabilities associated with a user.
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

    var Capabilities = {

        /**
         * This is the list of cached capabilities.
         */
        capabilities: null,

        /**
         * Get the list of the user's capabilities.
         */
        getCapabilities: function(){
            // Get a promise ready
            var promise = jQuery.Deferred();

            // Get the capabilties
            if (this.capabilities === null) {

                var uri = Splunk.util.make_url("/splunkd/__raw/services/authentication/current-context?output_mode=json");

                // Fire off the request
                jQuery.ajax({
                    url: uri,
                    type: 'GET',
                    success: function (result) {
                        if (result !== undefined) {
                            this.capabilities = result.entry[0].content.capabilities;
                            promise.resolve(this.capabilities);
                        }
                        else {
                            promise.reject();
                        }
                    }.bind(this),
                    error: function () {
                        promise.reject();
                    }.bind(this)
                });
            }

            // If we already got them, then just return the capabilities
            else {
                promise.resolve(this.capabilities);
            }

            return promise;
        },

        /**
         * Determine if the user has the given capability.
         * 
         * @param capability The name of the capability to see if the user has.
         */
        hasCapability: function (capability) {

            // Get a promise ready
            var promise = jQuery.Deferred();

            $.when(this.getCapabilities()).done(function (capabilities) {

                // Determine if the user should be considered as having access
                if ($C.SPLUNKD_FREE_LICENSE) {
                    promise.resolve(true);
                }
                else {
                    promise.resolve($.inArray(capability, this.capabilities) >= 0);
                }
            }.bind(this));

            return promise;

        }
    };

    return Capabilities;
});
