/* Separate-process camera reader used only by the hardware integration test. */
#include "../../pylibobs/native/macos_camera.m"
#include <unistd.h>

static int pixel_r, pixel_g, pixel_b;
static uint32_t pixel_format, pixel_width, pixel_height;

static bool sample_color(CMSampleBufferRef sample, bool red) {
    CVImageBufferRef image = CMSampleBufferGetImageBuffer(sample);
    if (!image || CVPixelBufferLockBaseAddress(image, kCVPixelBufferLock_ReadOnly)) return false;
    uint32_t format = CVPixelBufferGetPixelFormatType(image);
    int r = 0, g = 0, b = 0;
    size_t x = CVPixelBufferGetWidth(image) / 2;
    size_t y = CVPixelBufferGetHeight(image) / 2;
    if (format == kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange) {
        uint8_t *luma = CVPixelBufferGetBaseAddressOfPlane(image, 0);
        uint8_t *chroma = CVPixelBufferGetBaseAddressOfPlane(image, 1);
        double yy = (luma[y * CVPixelBufferGetBytesPerRowOfPlane(image, 0) + x] - 16) * 255.0 / 219.0;
        size_t index = (y / 2) * CVPixelBufferGetBytesPerRowOfPlane(image, 1) + (x / 2) * 2;
        double u = (chroma[index] - 128) * 255.0 / 224.0;
        double v = (chroma[index + 1] - 128) * 255.0 / 224.0;
        r = yy + 1.5748 * v; g = yy - 0.187324 * u - 0.468124 * v; b = yy + 1.8556 * u;
    } else if (format == kCVPixelFormatType_32BGRA) {
        uint8_t *pixel = CVPixelBufferGetBaseAddress(image) + y * CVPixelBufferGetBytesPerRow(image) + x * 4;
        b = pixel[0]; g = pixel[1]; r = pixel[2];
    }
    CVPixelBufferUnlockBaseAddress(image, kCVPixelBufferLock_ReadOnly);
    pixel_r = r; pixel_g = g; pixel_b = b;
    pixel_format = format; pixel_width = CVPixelBufferGetWidth(image); pixel_height = CVPixelBufferGetHeight(image);
    return red ? r > 200 && g < 40 && b < 40 : b > 200 && g < 40 && r < 40;
}

int main(int argc, char **argv) { @autoreleasepool {
    if (argc != 2) return 2;
    CameraSink target = {0};
    if (find_sink(argv[1], &target)) return 3;
    CMIOObjectPropertyAddress address = property(kCMIODevicePropertyStreams);
    UInt32 size = 0, used = 0;
    if (CMIOObjectGetPropertyDataSize(target.device, &address, 0, NULL, &size)) return 4;
    CMIOStreamID *streams = calloc(1, size), input = 0;
    if (!streams) return 5;
    if (!CMIOObjectGetPropertyData(target.device, &address, 0, NULL, size, &used, streams)) {
        for (UInt32 index = 0; index < used / sizeof(*streams); index++) {
            UInt32 direction = 0;
            if (!read_property(streams[index], kCMIOStreamPropertyDirection, sizeof(direction), &direction)
                && direction == 1) { input = streams[index]; break; }
        }
    }
    free(streams);
    if (!input) return 6;
    CMSimpleQueueRef queue = NULL;
    if (CMIOStreamCopyBufferQueue(input, queue_changed, NULL, &queue) || !queue) return 7;
    if (CMIODeviceStartStream(target.device, input)) { CFRelease(queue); return 8; }
    puts("READER_READY"); fflush(stdout);
    bool red = false, blue = false;
    uint32_t frames = 0;
    CFAbsoluteTime deadline = CFAbsoluteTimeGetCurrent() + 12;
    while ((!red || !blue) && CFAbsoluteTimeGetCurrent() < deadline) {
        CMSampleBufferRef sample = (CMSampleBufferRef)CMSimpleQueueDequeue(queue);
        if (sample) {
            if (!red && sample_color(sample, true)) {
                red = true;
                puts("RED_SEEN"); fflush(stdout);
            }
            // Ignore a stale blue frame retained before this producer's red.
            blue = blue || (red && sample_color(sample, false));
            frames++;
            CFRelease(sample);
        } else usleep(1000);
    }
    CMIODeviceStopStream(target.device, input);
    CMSimpleQueueRef detached = NULL;
    CMIOStreamCopyBufferQueue(input, NULL, NULL, &detached);
    if (detached) CFRelease(detached);
    const void *sample;
    while ((sample = CMSimpleQueueDequeue(queue))) CFRelease(sample);
    CFRelease(queue);
    printf("{\"red\":%s,\"blue\":%s,\"frames\":%u,\"last_rgb\":[%d,%d,%d],\"format\":%u,\"size\":[%u,%u]}\n",
           red ? "true" : "false", blue ? "true" : "false", frames, pixel_r, pixel_g, pixel_b,
           pixel_format, pixel_width, pixel_height);
    return red && blue ? 0 : 9;
} }
