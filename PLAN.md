# Plan

## Problem (as given)
> Build a full-stack app that allows users to convert videos in to grayscale and then download the video. Show upload, processing, and error statuses. Backend should call external API service for grayscale transformation. 
> Step 2: Support Long videos, return full video length in the right order. Show progress and support 2 video uploads simultaneoulsy 
> When a user uploads a video that is > 10 seconds long, the application will begin the spliceing automatically, send each spliced part through the API, and receive the responses from the api, and resplice them together, and then display them on the front end. This is the goal/plan of the application right now. It will also support simultaneous uploads

## Clarifying questions and answers
- Who is the user / core action? -> User-facing 
- What does "done" look like at the end?  -> Working front-end, a back-end that calls the external API, front end displays original and grayscale video, user can download grayscale version. 
- Persistence needed? Multi-user / auth? (default: single hardcoded user) -> No authentication, just one user for now 
- Scale: rough number of items? -> One video at a time 
- Real-time / concurrent editing? -> Needs to be able to accept 2 video uploads > 10 seconds at the same time and display both when completed. 
- External APIs? Can I mock them? -> One external API, /api/transform
- Length of videos? -> at least 1hr long videos 

## Scope
**Building (MVP):**
1. Backend that makes a post request on the api/transform API. The api takes in a original MP4 video and and returns a grayscale version. 
2. Front-end should allow user to upload a video and call on the backend to start grayscale.
3. Status of the API should be reflected on the front-end, ex. upload progress, processing status, errors.
4. Display both original and grayscale versions.
5. Allow download of grayscale version. 
6. Splices longer videos into smaller < 10 sec portions to pass through to API, needs a way to re-splice back together
7. Support the upload of 2 videos being uploaded simultaneously and display both grayscale videos alongside the original when completed. 
8. Have a way to track the splicing of the video so we can put them together again. (queueing the spliced videos would work but would be too slow for large video sizes.)
9. Splice videos every <10 seconds, check the size of the spliced videos. If videos are too large, splice it in half again repeatedly until the videos are <3 000 000 


**Skipping (and why):**
- 

**Stretch, if time allows:**
- There needs to be some verification function that ensures that the uploaded video fits within the constraints of the API input. 

## API Curl Request shape:
- curl -X POST "$BASE_URL/api/transform" -H "Authorization: Bearer $SESSION_TOKEN" -F "clip=@segment.mp4;type=video/mp4" --output transformed.mp4
- API returns the grayscale mp4 into the same place that the API was called and downloaded.

## API Constraints:
- Each clip: at most 10 seconds and 3,000,000 bytes. Full multipart request: 3.2 MB.
H.264 MP4 up to 1920×1080 and 600 frames per clip.
Success: 200 video/mp4, grayscale video.


## Edge cases to handle
-

## Known limitations / what I'd do next
-