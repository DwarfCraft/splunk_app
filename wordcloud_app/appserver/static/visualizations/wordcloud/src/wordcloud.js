/*
 * Wordcloud visualization view class
 */
define([
            'jquery',
            'underscore',
            'vizapi/SplunkVisualizationBase',
            'vizapi/SplunkVisualizationUtils',
            'd3',
            'd3-cloud'
        ],
        function(
            $,
            _,
            SplunkVisualizationBase,
            vizUtils,
            d3,
            cloud
        ) {
  
    // Extend from SplunkVisualizationBase
    return SplunkVisualizationBase.extend({
  
        initialize: function() {
            SplunkVisualizationBase.prototype.initialize.apply(this, arguments);
            this.$el = $(this.el);
        },

        // Optionally implement to format data returned from search. 
        // The returned object will be passed to updateView as 'data'
        formatData: function(data) {
            var rows = data.rows;
            var fields = data.fields;
            var max = 0, min = 0;

            var colorBy = this._getEscapedProperty('colorBy') || 'colorMode';


            if (fields.length > 0 && fields.length < 2) {
                throw new SplunkVisualizationBase.VisualizationError(
                    'You need at least 2 data dimensions to create a wordcloud (word, count)'
                );
            }

            if (colorBy != 'colorMode' && fields.length > 0 && fields.length < 3) {
                throw new SplunkVisualizationBase.VisualizationError(
                    'You need at least 3 data dimensions to create a wordcloud w/ field colorization: (word, count, colorString)'
                );
            }

            max = _.max(rows, function(row) {
                if (_.isNaN(+row[1])) {
                    throw new SplunkVisualizationBase.VisualizationError(
                        'Your second data dimension must be a number'
                    );
                }
                return +row[1];
            })[1];
            min = _.min(rows, function(row) { return +row[1] })[1];

            data['max'] = max;
            data['min'] = min;

            return data;
        },

        getFrequencyClass: function(count, maxCount) {
            // what are frequency classes?
            // https://en.wikipedia.org/wiki/Word_lists_by_frequency#Statistics
            return Math.floor(.5 - Math.log(count / maxCount, 2));
        },

        // Implement updateView to render a visualization.
        //  'data' will be the data object returned from formatData or from the search
        //  'config' will be the configuration property object
        updateView: function(data, config) {
            if (!data || data.rows.length < 1) {
                return
            }

            this.$el.empty();


            var elHeight = this.$el.height();
            var wordMaxHeight = elHeight / 6;
            var words = [];
            var rows = data.rows;
            var row, frequencyClass;
            var min = +data.min;
            var max = +data.max;

            var alignmentModes = {
                horizontal: function() { return 0; },
                vertical: function() { return 90; },
                hovert: function(i) { return i%2===0?0:90; },
                random: function() { return (Math.random()*360) >> 0; }
            }

            var alignmentMode = this._getEscapedProperty('alignmentMode') || 'horizontal';
            if (!alignmentModes[alignmentMode]) {
                alignmentMode = 'horizontal';
            }

            // todo: use this:
            //var useColors = vizUtils.normalizeBoolean(this._getEscapedProperty('useColors'));
            var useColors = this._getEscapedProperty('useColors') == 'true';
            var colorBy = this._getEscapedProperty('colorBy') || 'colorMode';
            var colorMode = this._getEscapedProperty('colorMode') || 'categorical';
            var numOfBins = +this._getEscapedProperty('numOfBins') || 3;
            var maxColor = this._getEscapedProperty('maxColor') || '#fff';
            var minColor = this._getEscapedProperty('minColor') || '#000';
            var splunkTasticMode = this._getEscapedProperty('splunkTastic') == 'true';

            var backgroundColor = this._getEscapedProperty('backgroundColor') || '#fff';
            $(this.el).css('background-color', backgroundColor);

            // this selects the highest frequency class. 
            // it's either at the bottom, or at the top of the rows
            // highest frequency class means it's in the group of least common words
            var maxFrequencyClass = this.getFrequencyClass(_.min(rows, function(el) { return +el[1]; })[1], data.max);
            
            // color binning 
            var colorCategories = _.unique(_.map(rows, function(row) { return +row[1]; }));
            var domain = [];
            var range = [];
            var interpolateNum = d3.interpolateRound(min, max);
            var interpolateColor = d3.interpolateHcl(minColor, maxColor); //Rgb, Hcl, Hsl


            if (numOfBins == -1) {
                numOfBins = colorCategories.length;
            }
            var colors = [ "#1e93c6", "#f2b827", "#d6563c", "#6a5c9e", "#31a35f"];

            for(var x = 0; x < numOfBins; x++) {
                domain.push(interpolateNum(x/(numOfBins)));
                range.push(colorMode == 'categorical' ? colors[x%colors.length] : interpolateColor(x/(numOfBins)));
            }
            
            var colorScale = d3.scale.ordinal()
                        .domain(domain)
                        .range(range);

            var categoryDomain = [];
            var categoryRange = [];

            // binning 
            for (var i = 0; i < colorCategories.length; i++) {
                var colorCategory = colorCategories[i];
                var bin = -1;
                for (var o = 0; o < domain.length; o++) {
                    if (domain[o] <= colorCategory) {
                        bin++;
                        continue;
                    }
                }
                categoryDomain.push(colorCategory);
                categoryRange.push(domain[bin]);
            }
            var categoryScale = d3.scale.ordinal()
                                    .domain(categoryDomain)
                                    .range(categoryRange);

            /*var colorScale = d3.scale.linear()
                .domain([0, maxFrequencyClass])
                .range([ "#1e93c6", "#f2b827", "#d6563c", "#6a5c9e", "#31a35f"]);
                // todo: use this
                //.range(vizUtils.getColorPalette());*/



            _.each(rows, function(row) {
                frequencyClass = this.getFrequencyClass(+row[1], data.max);
                words.push({
                    text: row[0],
                    size: (wordMaxHeight * 1 / (frequencyClass + 1)),
                    color: useColors ? (colorBy == 'colorMode' ? colorScale(categoryScale(+row[1])) : row[2]) : (backgroundColor == '#fff' ? '#222' : '#fff')
                });
            }, this);

            if (splunkTasticMode) {
                words.push({
                    text: 'splunk>',
                    size: wordMaxHeight*1.5,
                    color: backgroundColor == '#fff' ? '#333' : '#65a637'
                });
            }

            var that = this;
            var layout = cloud()
                .size([this.$el.width(), elHeight])
                .words(words)
                .padding(0)
                // for now let's just do horizontal word alignment
                .rotate(function(d, i) { return alignmentModes[alignmentMode](i); })
                .font('Impact')
                .fontSize(function(d) { return d.size; })
                .on('end', function() {
                    d3.select(that.el).append('svg')
                        .attr('width', layout.size()[0])
                        .attr('height', layout.size()[1])
                        .append('g')
                        .attr('transform', 'translate(' + layout.size()[0] / 2 + ',' + layout.size()[1] / 2 + ')')
                        .selectAll('text')
                        .data(words)
                        .enter().append('text')
                        .style('font-size', function(d) { return d.size + 'px'; })
                        .style('font-family', function(d) { return  splunkTasticMode && d.text == 'splunk>' ? 'Splunk Icons' : 'Impact'; })
                        .style('fill', function(d, i) { return d.color; })
                        .style('opacity', function(d) { return splunkTasticMode && d.text != 'splunk>' ? .4 : 1; })
                        .attr('text-anchor', 'middle')
                        .attr('transform', function(d) {
                            return 'translate(' + [d.x, d.y] + ')rotate(' + d.rotate + ')';
                        })
                        .attr('class', function(d) { return splunkTasticMode ? (d.text != 'splunk>' ? 'blink' : 'splunk') : ''; })
                        .style('animation-delay', function(d, i) { return Math.random() + 's'; })
                        .text(function(d) { return d.text; })
                });

            layout.start();

            if (splunkTasticMode) {

            }
        },

        // Search data params
        getInitialDataParams: function() {
            return ({
                outputMode: SplunkVisualizationBase.ROW_MAJOR_OUTPUT_MODE,
                count: 10000
            });
        },

        // Override to respond to re-sizing events
        reflow: function() {
            this.invalidateUpdateView();
        },

        _getEscapedProperty: function(name) {
            var config = this.getCurrentConfig();
            var propertyValue = config[this.getPropertyNamespaceInfo().propertyNamespace + name];
            return vizUtils.escapeHtml(propertyValue);
        }
    });
});