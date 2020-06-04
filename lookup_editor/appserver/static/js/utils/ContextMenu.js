define([], function () {
    var self = this;
  return function (el, x, y, e) {
    var items = [];

    var jexcel = this.jexcel;

    if (y == null) {
      // Insert a new column
      if (this.lookup_type === "csv") {
        items.push({
          title: jexcel.options.text.insertANewColumnBefore,
          onclick: function () {
            jexcel.insertColumn(1, parseInt(x), 1);
          },
        });
      }

      if (this.lookup_type === "csv") {
        items.push({
          title: jexcel.options.text.insertANewColumnAfter,
          onclick: function () {
            jexcel.insertColumn(1, parseInt(x), 0);
          },
        });
      }

      // Delete a column
      if (this.lookup_type === "csv") {
        items.push({
          title: jexcel.options.text.deleteSelectedColumns,
          onclick: function () {
            jexcel.deleteColumn(
              jexcel.getSelectedColumns().length ? undefined : parseInt(x)
            );
          },
        });
      }

      // Rename column
      if (this.lookup_type === "csv") {
        items.push({
          title: jexcel.options.text.renameThisColumn,
          onclick: function () {
            jexcel.setHeader(x);
          },
        });
      }

      items.push({
        title: "Insert a new row",
        onclick: function () {
          jexcel.insertRow(1, 0);
        },
      });

      // Line
      if (this.lookup_type === "csv") {
          items.push({ type: "line" });
      }

      // Sorting
      items.push({
        title: jexcel.options.text.orderAscending,
        onclick: function () {
          jexcel.orderBy(x, 0);
        },
      });
      items.push({
        title: jexcel.options.text.orderDescending,
        onclick: function () {
          jexcel.orderBy(x, 1);
        },
      });
    } else {
      // Insert new row
      items.push({
        title: jexcel.options.text.insertANewRowBefore,
        onclick: function () {
          jexcel.insertRow(1, parseInt(y), 1);
        },
      });

      items.push({
        title: jexcel.options.text.insertANewRowAfter,
        onclick: function () {
          jexcel.insertRow(1, parseInt(y));
        },
      });

      items.push({
        title: jexcel.options.text.deleteSelectedRows,
        onclick: function () {
          jexcel.deleteRow(jexcel.getSelectedRows().length ? undefined : parseInt(y));
        },
      });
    }

    // Line
    items.push({ type: "line" });

    // Copy
    items.push({
      title: jexcel.options.text.copy,
      shortcut: "Ctrl + C",
      onclick: function () {
        jexcel.copy(true);
      },
    });

    // Paste
    if (navigator && navigator.clipboard) {
      items.push({
        title: jexcel.options.text.paste,
        shortcut: "Ctrl + V",
        onclick: function () {
          if (jexcel.selectedCell) {
            navigator.clipboard.readText().then(function (text) {
              if (text) {
                jexcel.current.paste(
                  jexcel.selectedCell[0],
                  jexcel.selectedCell[1],
                  text
                );
              }
            });
          }
        },
      });
    }

    // Save
    if (jexcel.options.allowExport) {
      items.push({
        title: jexcel.options.text.saveAs,
        shortcut: "Ctrl + S",
        onclick: function () {
          jexcel.download();
        },
      });
    }

    return items;
  };
});
