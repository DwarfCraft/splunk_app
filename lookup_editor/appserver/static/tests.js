/**
 * This file is a chunk of Javascript this is useful for running Jasmine tests within Splunk.
 * 
 * To use this, you will need to:
 * 
 *  1) Make a view that includes this Javascript. Something like this:
 * 
 *     <dashboard script="tests.js" stylesheet="tests.css" isDashboard="false" isVisible="false" hideEdit="true">
 *         <label>my_app_name Tests</label>
 *         <row>
 *         </row>
 *     </dashboard>
 * 
 *  2) Make a list of your tests in your app at /appserver/static/js/tests/test_index.json which indicates where your tests are.
 *     Something like this:
 * 
 *     {
 *         "test_list_view": "../app/my_app_name/js/tests/TestSomething"
 *     }
 * 
 *  3) Create your test views
 *     In the example above, your would make the test view in:
 * 
 *     my_app_name/js/tests/TestSomething.js
 */

// This variable will hold the name of the app where the test resources reside (specifically console.js)
var app = null;

/**
 * Run the tests that are defined in the testScripts parameter.
 */
function runJasmineTests($, testScripts) {
    // Set up the paths for require.js to load Jasmine
    var paths = {
        'jasmine': 'https://cdnjs.cloudflare.com/ajax/libs/jasmine/2.8.0/jasmine',
        'jasmine-html': 'https://cdnjs.cloudflare.com/ajax/libs/jasmine/2.8.0/jasmine-html',
        'jasmine-boot': 'https://cdnjs.cloudflare.com/ajax/libs/jasmine/2.8.0/boot',
    };

    // Combine the Jasmine paths with the test script paths
    paths = $.extend(paths, testScripts);

    // Configure require.js to load the test scripts as well as the Jasmine dependencies
    require.config({
        paths: paths,
        shim: {
            'jasmine-html': {
                deps: ['jasmine'],
            },
            'jasmine-boot': {
                deps: ['jasmine', 'jasmine-html'],
            },
        }
    });

    // Now, load the dependencies and run the tests scripts
    require([
        'jquery',
        'underscore',
        'backbone',
        'jasmine-boot',
        'jasmine-html',
        'splunkjs/mvc/utils',
        'css!' + 'https://cdnjs.cloudflare.com/ajax/libs/jasmine/2.8.0/jasmine.css',
    ], function() {
        var testSpecs = Object.keys(testScripts);

        require(testSpecs, function() {
            window.onload();
        });
    }.bind(this));
}

/**
 * Load the collection of tests for the given app.
 */
function loadSuitesForApp($, app) {
    var deferred = $.Deferred();
    var uri = Splunk.util.make_url('static/app/' + encodeURIComponent(app) + '/js/tests/test_index.json');

    $.ajax({
        url: uri,
        type: 'GET',
        cache: false,
        async: true,
    }).done(function(result){
        if (result === undefined) {
            deferred.reject(result);
        } else if (typeof result === 'string') {
            deferred.resolve(JSON.parse(result));
        } else if (typeof result === 'object') {
            deferred.resolve(result);
        } else {
            deferred.reject(result);
        }
    }.bind(this)).fail(function(result){
        deferred.reject(result);
    });
    return deferred.promise();
}
/**
 * Start the tests for the app that this file resides in.
 */
function runTests(testApps) {
    require(['jquery',
             '../app/' + app + '/js/lib/console'
    ], function($, console) {
        var suites = testApps.map(function(suite){
            loadSuitesForApp($, suite);
        }.bind(this));

        // Load all of the test suites before running the tests
        $.when(...suites).done((...suite) => {
            // Merge the tests together into a single array
            var tests = {};
            suite.forEach(function(test){
                $.extend(tests, test);
            }.bind(this));

            // Run the tests
            runJasmineTests($, tests);
        }).fail(err => {
            console.log(err);
        });
    })();
}

/**
 * Load the utils so that we can get the current app name and then run the tests.
 */
require(['splunkjs/mvc/utils'],
    function(utils) {
        if(app === null){
            app = utils.getCurrentApp();
        }
        runTests([utils.getCurrentApp()]);
    }
);
