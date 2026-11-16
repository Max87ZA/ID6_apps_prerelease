// Native NBT EVO RA plugin. Models are touched only on the HMI dispatcher.
// Network diagnostics run in the separate collector process, never in HmiMain3D.
#include "plugin_factory.h"
#include "gauge_core.h"
#include "dial_scales.h"
#include "diagnostic_worker.h"
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/wait.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#if defined(__arm__)
// C++98 target ABI gates. Host builds have 64-bit pointers and cannot prove these.
typedef char bd_pointer_size[(sizeof(void*)==4) ? 1 : -1];
typedef char bd_parcel_size[(sizeof(bmw::Parcel)==20) ? 1 : -1];
typedef char bd_message_size[(sizeof(bmw::Message)==80 && __alignof__(bmw::Message)==8) ? 1 : -1];
typedef char bd_std_string_size[(sizeof(std::string)==4) ? 1 : -1];
typedef char bd_delegate_size[(sizeof(bmw::Delegate<bool,const bmw::Parcel&>)==8) ? 1 : -1];
#endif

namespace {
// In the installed AppFramework, this message reads a UInt32 key from its
// Parcel and dispatches through the primary invokeDataUpdate virtual.
const unsigned kDataUpdateMessage = 0x40000003u;
const unsigned kPollKey = 0x4244504cu; // BDPL, private to this app
const unsigned kActivePollIntervalMs = 25u;
const unsigned kIdlePollIntervalMs = 250u;
const char kGateway[] = "169.254.24.115";
const char kCollector[] = "/var/opt/hmi/data/ID5/Plugins/BoostDeck/boostdeck-collector-qnx";
const unsigned kBarCount = sizeof(kDialScales)/sizeof(kDialScales[0]);
#ifdef PERF_LAB
typedef char dial_count_check[kBarCount + 1 == BD_COUNT ? 1 : -1];
const unsigned kEthanolFirst = 56100u;
const unsigned kEthanolSteps = 20u;
#else
typedef char dial_count_check[kBarCount == BD_COUNT ? 1 : -1];
#endif
#ifdef HYBRID_PAGE
#ifndef PERF_LAB
#error HYBRID_PAGE needs PERF_LAB (it uses the units setting)
#endif
const unsigned kHybridValues = 7u;        // values in the collector's NBH2 datagram
const unsigned kHybridTiles = 8u;         // tiles on the Hybrid page (one is derived)
const unsigned kHybridState = 105u;
const unsigned kHybridFirstModel = 120u;  // tile value labels 120..127
const unsigned kHybridFirstImage = 130u;  // tile bar images 130..137
const unsigned kHybridFirstBar = 500u;    // tile bar components 500..507
const unsigned kHybridStaleMs = 6000u;
#endif
}

class BoostDeck : public bmw::PluginApp {
    int fd_;
    unsigned poll_generation_;
    bd_frame frame_;
    uint64_t received_;
    pid_t collector_;
    bool stopping_;
    bool gauges_visible_;
    unsigned color_;
#ifdef PERF_LAB
    bool metric_;
#endif
    uint64_t retry_at_;
    void startVisibleCollector();
    void selectColor(unsigned color);
    char labels_[BD_COUNT][128];
    unsigned images_[BD_COUNT];
#ifdef HYBRID_PAGE
    // Second screen (HMI state 105): eight tiles fed by the collector's NBH2 datagram.
    unsigned pages_;                 // bit 0: gauges visible, bit 1: hybrid page visible
    double hybrid_[kHybridValues];
    unsigned hybrid_valid_;
    uint64_t hybrid_received_;
    char hybrid_labels_[kHybridTiles][64];
    unsigned hybrid_images_[kHybridTiles];
    void parseHybrid(const char* data, size_t size);
    void refreshHybrid();
#endif
    void setVisible(bool visible);
    void postPoll();
public:
    BoostDeck(bmw::IDispatcher& d, bmw::BasicString<char> name, unsigned maj, unsigned mn,
              bmw::RHMIInterfaceVersion rhmi, const bmw::Bundle& cfg, const bmw::Bundle& res)
        : bmw::PluginApp(d,name,maj,mn,rhmi,cfg,res), fd_(-1), poll_generation_(0),
          received_(0), collector_(-1), stopping_(false), gauges_visible_(false),
          color_(0),
#ifdef PERF_LAB
          metric_(true),
#endif
          retry_at_(0) {
#ifdef HYBRID_PAGE
        pages_=0;
#endif
        resetDisplay();
    }
    virtual ~BoostDeck() { shutdown(); }
    virtual bool onInit();
    virtual bool onFinalize() { shutdown(); return true; }
    virtual bool invokeDataUpdate(unsigned key, const bmw::Parcel& data);
    bool gaugeVisibility(const bmw::Parcel&);
#ifdef HYBRID_PAGE
    bool hybridVisibility(const bmw::Parcel&);
#endif
    template <unsigned Color> bool changeColor(const bmw::Parcel&) {
        selectColor(Color);
        return true;
    }
#ifdef PERF_LAB
    template <bool Metric> bool changeUnits(const bmw::Parcel&) {
        metric_=Metric;
        refresh();
        return true;
    }
#endif
    void reapCollector() {
        if (collector_ <= 0) return;
        pid_t ended = waitpid(collector_, 0, WNOHANG);
        if (ended == collector_ || (ended < 0 && errno == ECHILD)) {
            collector_ = -1;
            stopping_ = false;
        }
    }
    void stopCollector() {
        reapCollector();
        if (collector_ > 0 && !stopping_) {
            kill(collector_, SIGTERM);
            stopping_ = true;
        }
    }
    void shutdown() {
        gauges_visible_=false;
#ifdef HYBRID_PAGE
        pages_=0;
#endif
        stopCollector();
        if (fd_>=0) { close(fd_); fd_=-1; }
    }
    void resetDisplay() {
        memset(&frame_,0,sizeof frame_); memset(labels_,0,sizeof labels_);
        memset(images_,0,sizeof images_);
        received_=0;
#ifdef HYBRID_PAGE
        memset(hybrid_,0,sizeof hybrid_); memset(hybrid_labels_,0,sizeof hybrid_labels_);
        memset(hybrid_images_,0,sizeof hybrid_images_);
        hybrid_valid_=0; hybrid_received_=0;
#endif
    }
    void refresh();
    void poll();
};

bool BoostDeck::onInit() {
    shutdown();
    resetDisplay();
    struct sockaddr_in a;
    fd_=socket(AF_INET,SOCK_DGRAM,0);
    memset(&a,0,sizeof a); a.sin_family=AF_INET; a.sin_port=htons(BD_UDP_PORT);
    a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if (fd_>=0 && (fcntl(fd_,F_SETFL,O_NONBLOCK)<0 || fcntl(fd_,F_SETFD,FD_CLOEXEC)<0 ||
        bind(fd_,reinterpret_cast<struct sockaddr*>(&a),sizeof a)<0)) {
        close(fd_); fd_=-1;
    }
    bmw::Delegate<bool,const bmw::Parcel&> action;
    action.m_obj=this;
    // BMW sends event 11 with a bool when this HMI state becomes visible or hidden.
    action.m_exec=&bmw::Delegate<bool,const bmw::Parcel&>::execImpl<BoostDeck,&BoostDeck::gaugeVisibility>;
    addHandler(100u,11u,action);
#ifdef HYBRID_PAGE
    action.m_exec=&bmw::Delegate<bool,const bmw::Parcel&>::execImpl<BoostDeck,&BoostDeck::hybridVisibility>;
    addHandler(kHybridState,11u,action);
#endif
    typedef bmw::Delegate<bool,const bmw::Parcel&> Action;
    typedef bool (*Handler)(void*,const bmw::Parcel&);
    static const Handler colorHandlers[] = {
        &Action::execImpl<BoostDeck,&BoostDeck::changeColor<0> >,
        &Action::execImpl<BoostDeck,&BoostDeck::changeColor<1> >,
        &Action::execImpl<BoostDeck,&BoostDeck::changeColor<2> >,
        &Action::execImpl<BoostDeck,&BoostDeck::changeColor<3> >,
        &Action::execImpl<BoostDeck,&BoostDeck::changeColor<4> >,
        &Action::execImpl<BoostDeck,&BoostDeck::changeColor<5> >,
        &Action::execImpl<BoostDeck,&BoostDeck::changeColor<6> >,
        &Action::execImpl<BoostDeck,&BoostDeck::changeColor<7> >,
        &Action::execImpl<BoostDeck,&BoostDeck::changeColor<kMulticolor> >
    };
    typedef char color_handler_count[(sizeof colorHandlers/sizeof colorHandlers[0] ==
                                      sizeof kColorNames/sizeof kColorNames[0]) ? 1 : -1];
    (void)sizeof(color_handler_count);
    for (unsigned i=0;i<sizeof colorHandlers/sizeof colorHandlers[0];++i) {
        action.m_exec=colorHandlers[i];
        addHandler(40u+i,action);
    }
#ifdef PERF_LAB
    action.m_exec=&Action::execImpl<BoostDeck,&BoostDeck::changeUnits<false> >;
    addHandler(49u,action);
    action.m_exec=&Action::execImpl<BoostDeck,&BoostDeck::changeUnits<true> >;
    addHandler(59u,action);
#endif
    selectColor(color_);
    bmw::Parcel visible(true);
    for (unsigned i=0;i<kBarCount;++i) setProperty(200u+i,3u,visible);
#ifdef HYBRID_PAGE
    for (unsigned i=0;i<kHybridTiles;++i) setProperty(kHybridFirstBar+i,3u,visible);
    // Labels shown beside the toolbar icons when the side toolbar is open.
    updateModel(140u,bmw::BasicString<char>("Engine"));
    updateModel(141u,bmw::BasicString<char>("Hybrid"));
#endif
    refresh();
    if (fd_>=0) {
        ++poll_generation_;
        postPoll();
    }
    return true;
}

bool BoostDeck::gaugeVisibility(const bmw::Parcel& event) {
    bool visible;
    if (!event.readBool(visible)) return true;
#ifdef HYBRID_PAGE
    pages_ = visible ? pages_|1u : pages_&~1u;
    visible = pages_!=0;
#endif
    setVisible(visible);
    return true;
}

#ifdef HYBRID_PAGE
bool BoostDeck::hybridVisibility(const bmw::Parcel& event) {
    bool visible;
    if (!event.readBool(visible)) return true;
    pages_ = visible ? pages_|2u : pages_&~2u;
    setVisible(pages_!=0);
    return true;
}
#endif

// The collector runs while either screen is showing.
void BoostDeck::setVisible(bool visible) {
    if (gauges_visible_==visible) return;
    gauges_visible_=visible;
    if (visible) {
        retry_at_=0;
        startVisibleCollector();
    } else {
        stopCollector();
        received_=0;
        memset(&frame_,0,sizeof frame_);
#ifdef HYBRID_PAGE
        hybrid_received_=0;
#endif
        refresh();
    }
}

void BoostDeck::startVisibleCollector() {
    if (!gauges_visible_ || collector_>0 || fd_<0 ||
        bd_mono_ms()<retry_at_) return;
    const char *args[]={kCollector,"--host",kGateway,"--session",
#if defined(PERF_LAB) && defined(HV_SOC_BAR)
                       "--hv-soc",
#elif defined(PERF_LAB)
                       "--ethanol",
#endif
                       0};
    collector_=launch(args,-1);
    retry_at_=bd_mono_ms()+2000;
}

void BoostDeck::selectColor(unsigned color) {
    color_=color;
    char label[48];
    snprintf(label,sizeof label,"Selected: %s",kColorNames[color_]);
    updateModel(110u,bmw::BasicString<char>(label));
    refresh();
}

void BoostDeck::postPoll() {
    // The framework copies the Message and Parcel into its own queue. Entries
    // carry only data, so clearing the queue needs no code from this module.
    bmw::Parcel data;
    data.writeUInt32(kPollKey);
    data.writeUInt32(poll_generation_);
    bmw::Message message(kDataUpdateMessage, data);
    post(message, collector_ > 0 ? kActivePollIntervalMs : kIdlePollIntervalMs);
}

bool BoostDeck::invokeDataUpdate(unsigned key, const bmw::Parcel& data) {
    if (key!=kPollKey) return bmw::PluginApp::invokeDataUpdate(key,data);
    unsigned generation;
    if (!data.readUInt32(generation)) return false;
    if (fd_<0 || generation!=poll_generation_) return true;
    poll();
    if (fd_>=0 && generation==poll_generation_) postPoll();
    return true;
}

void BoostDeck::poll() {
    reapCollector();
    startVisibleCollector();
    // A bounded non-blocking drain: at most 8 * 512 bytes per UI tick.
    char data[BD_MAX_PACKET];
    for (unsigned n=0;fd_>=0 && n<8;++n) {
        ssize_t k=recv(fd_,data,sizeof data,0);
        if (k<=0) break;
        bd_frame next;
        if (gauges_visible_ && !stopping_ && bd_parse(data,static_cast<size_t>(k),&next) &&
            next.sent_ms && next.sent_ms<=bd_mono_ms() &&
            (!received_ || next.sent_ms>=received_)) {
            frame_=next; received_=next.sent_ms; // queued UDP does not reset sample age
        }
#ifdef HYBRID_PAGE
        else if (gauges_visible_ && !stopping_ && k>5 && !memcmp(data,"NBH2 ",5))
            parseHybrid(data,static_cast<size_t>(k));
#endif
    }
    refresh();
}

#ifdef HYBRID_PAGE
void BoostDeck::parseHybrid(const char* data, size_t size) {
    char text[200];
    unsigned long long sent;
    unsigned valid;
    double v[kHybridValues];
    if (size>=sizeof text || memchr(data,0,size)) return;
    memcpy(text,data,size); text[size]=0;
    if (sscanf(text,"NBH2 %llu %u %lf %lf %lf %lf %lf %lf %lf",&sent,&valid,
               &v[0],&v[1],&v[2],&v[3],&v[4],&v[5],&v[6])!=9) return;
    if (!sent || sent>bd_mono_ms() || valid>=(1u<<kHybridValues) ||
        (hybrid_received_ && sent<hybrid_received_)) return;
    for (unsigned i=0;i<kHybridValues;++i) hybrid_[i]=v[i];
    hybrid_valid_=valid;
    hybrid_received_=sent;
}

void BoostDeck::refreshHybrid() {
    // Tiles in layout order (column by column, like the gauge page). Each takes one
    // datagram value, except petrol range, which is total range minus electric range.
    // Wire order: 0 electric km, 1 total km, 2 HV volts, 3 12 V volts, 4 oil C, 5 fuel %, 6 outside C.
    enum Kind { kDistance1, kDistance0, kPercent, kVolts0, kVolts1, kTemperature };
    static const struct { unsigned need; int a, b; Kind kind; double lo, hi; } tiles[kHybridTiles] = {
        {1u<<0,      0,-1, kDistance1,   0,  40},   // ELECTRIC RANGE
        {3u,         1, 0, kDistance0,   0, 600},   // PETROL RANGE
        {1u<<1,      1,-1, kDistance0,   0, 700},   // TOTAL RANGE
        {1u<<5,      5,-1, kPercent,     0, 100},   // FUEL LEVEL
        {1u<<2,      2,-1, kVolts0,    240, 340},   // HV VOLTAGE
        {1u<<3,      3,-1, kVolts1,     11,  15},   // 12 V BATTERY
        {1u<<4,      4,-1, kTemperature, 0, 150},   // OIL TEMP
        {1u<<6,      6,-1, kTemperature,-20, 40}    // OUTSIDE TEMP
    };
    const bool live = hybrid_received_ && bd_mono_ms()-hybrid_received_<kHybridStaleMs;
    for (unsigned i=0;i<kHybridTiles;++i) {
        char label[64];
        unsigned image = kBarFirst;
        if (live && (hybrid_valid_&tiles[i].need)==tiles[i].need) {
            double x=hybrid_[tiles[i].a];
            if (tiles[i].b>=0) x-=hybrid_[tiles[i].b];
            if (x<0 && tiles[i].kind!=kTemperature) x=0;
            switch (tiles[i].kind) {
            case kDistance1: snprintf(label,sizeof label,"%.1f %s",metric_ ? x : x*0.621371,metric_ ? "km" : "mi"); break;
            case kDistance0: snprintf(label,sizeof label,"%.0f %s",metric_ ? x : x*0.621371,metric_ ? "km" : "mi"); break;
            case kPercent:   snprintf(label,sizeof label,"%.0f%%",x); break;
            case kVolts0:    snprintf(label,sizeof label,"%.0f V",x); break;
            case kVolts1:    snprintf(label,sizeof label,"%.1f V",x); break;
            default:         snprintf(label,sizeof label,"%.0f %s",metric_ ? x : x*1.8+32,metric_ ? "\260C" : "\260F");
            }
            double fraction=(x-tiles[i].lo)/(tiles[i].hi-tiles[i].lo);
            if (fraction<0) fraction=0;
            if (fraction>1) fraction=1;
            const unsigned step=static_cast<unsigned>(fraction*kDialSteps+.5);
            if (step) {
                const unsigned palette = color_ == kMulticolor ? kMulticolor + i : color_;
                image += palette*kDialSteps+step;
            }
        } else strcpy(label,"--");
        if (image!=hybrid_images_[i]) {
            updateModel(kHybridFirstImage+i,bmw::ImageID(image));
            hybrid_images_[i]=image;
        }
        if (strcmp(label,hybrid_labels_[i])) {
            updateModel(kHybridFirstModel+i,bmw::BasicString<char>(label));
            strcpy(hybrid_labels_[i],label);
        }
    }
}
#endif

void BoostDeck::refresh() {
    uint64_t elapsed=received_ ? bd_mono_ms()-received_ : static_cast<uint64_t>(BD_STALE_MS);
    for (unsigned i=0;i<kBarCount;++i) {
        char label[128];
        const DialScale& scale = kDialScales[i];
        unsigned image = kBarFirst;
        if (received_ && bd_is_fresh(&frame_,i,elapsed)) {
            double x=frame_.value[i];
            const char *unit_space = *scale.unit ? " " : "";
            double reading = bd_display_value(i,x,0);
            if (i==BD_BOOST && fabs(reading)<0.05) reading=0;
#ifdef PERF_LAB
            if (metric_) {
                const char* units=i==BD_AFR ? "" : i==BD_TIMING ? "deg" :
                    i==BD_IAT || i==BD_TRANS || i==BD_COOLANT ? "\260C" : "bar";
                snprintf(label,sizeof label,"%.1f%s%s",bd_display_value(i,x,1),*units ? " " : "",units);
            } else snprintf(label,sizeof label,i==BD_RAIL ? "%.0f%s%s" : "%.1f%s%s",reading,unit_space,scale.unit);
#else
            const char *prefix = frame_.demo && i==BD_BOOST ? "Demo " : "";
            const char *format = i==BD_BOOST ? "%s%s   %+.1f%s%s"
                                : i==BD_RAIL ? "%s%s   %.0f%s%s"
                                : "%s%s   %.1f%s%s";
            snprintf(label,sizeof label,format,prefix,scale.name,reading,unit_space,scale.unit);
#endif
            double fraction=(x-scale.minimum)/(scale.maximum-scale.minimum);
            if (fraction<0) fraction=0;
            if (fraction>1) fraction=1;
            unsigned step=static_cast<unsigned>(fraction*kDialSteps+.5);
            if (step) {
                const unsigned palette = color_ == kMulticolor ? kMulticolor + i : color_;
                image += palette*kDialSteps+step;
            }
        } else {
#ifdef PERF_LAB
            strcpy(label,"--");
#else
            snprintf(label,sizeof label,"%s   --",scale.name);
#endif
        }
        if (image!=images_[i]) {
            updateModel(60u+i,bmw::ImageID(image));
            images_[i]=image;
        }
        if (strcmp(label,labels_[i])) {
            updateModel(50u+i,bmw::BasicString<char>(label));
            strcpy(labels_[i],label);
        }
    }
#ifdef PERF_LAB
    const bool valid = received_ && bd_is_fresh(&frame_,BD_ETHANOL,elapsed) &&
        frame_.value[BD_ETHANOL]>=0 && frame_.value[BD_ETHANOL]<=100;
    char ethanol[128];
#ifdef HV_SOC_BAR
    // The cluster showed 78 % for a raw 78.9 %, so truncate rather than round.
    if (valid) snprintf(ethanol,sizeof ethanol,"%d%%",static_cast<int>(frame_.value[BD_ETHANOL]));
#else
    if (valid) snprintf(ethanol,sizeof ethanol,"%.0f%%",frame_.value[BD_ETHANOL]);
#endif
    else strcpy(ethanol,"--");
    const unsigned step=valid ? static_cast<unsigned>(frame_.value[BD_ETHANOL]*kEthanolSteps/100.+.5) : 0;
    const unsigned ethanolImage=kEthanolFirst+(step ? color_*kEthanolSteps+step : 0);
    if (images_[BD_ETHANOL]!=ethanolImage) {
        updateModel(68u,bmw::ImageID(ethanolImage));
#ifdef HYBRID_PAGE
        updateModel(138u,bmw::ImageID(ethanolImage)); // same bar on the Hybrid page
#endif
        images_[BD_ETHANOL]=ethanolImage;
    }
    if (strcmp(labels_[BD_ETHANOL],ethanol)) {
        updateModel(58u,bmw::BasicString<char>(ethanol));
#ifdef HYBRID_PAGE
        updateModel(128u,bmw::BasicString<char>(ethanol));
#endif
        strcpy(labels_[BD_ETHANOL],ethanol);
    }
#endif
#ifdef HYBRID_PAGE
    refreshHybrid();
#endif
}

extern "C" {
PluginAppInfo pluginAppInfo = {1, "BoostDeck", "owner-development", 1,
                              create_app<BoostDeck>, destroy_app};
}
