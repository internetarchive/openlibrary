var gulp = require('gulp');
var less = require('gulp-less');
var path = require('path');
var cleanCSS = require('gulp-clean-css');

gulp.task('less', function () {
  return gulp.src('./static/css/*.less')
    .pipe(less({
      paths: [ path.join(__dirname) ]
    }))
    .pipe(cleanCSS({compatibility: 'ie8'}))
    .pipe(gulp.dest('./static/build'));
});
