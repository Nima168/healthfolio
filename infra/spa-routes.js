// CloudFront viewer-request function: page addresses without a file extension serve the React app.
function handler(event) {
  var request = event.request;
  if (!request.uri.includes('.')) {
    request.uri = '/index.html';
  }
  return request;
}
