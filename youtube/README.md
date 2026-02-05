# Creator Discovery

Find YouTube creators for collaboration opportunities — promotions, appearances, sponsorships, and partnerships.

## The Problem

Finding the right creators to partner with is time-consuming. Subscriber counts alone don't tell the full story. A channel with 50K subscribers but poor engagement is less valuable than one with 10K subscribers whose videos consistently reach their audience. Manual research across dozens of channels takes hours.

## The Solution

Creator Discovery automates the research process. Search by topic, filter by the metrics that matter, and instantly see which creators are worth reaching out to.

### What You Can Do

- **Search by topic** — Find creators in any niche using keyword search
- **Filter intelligently** — Narrow results by view counts, subscriber ranges, and recent activity
- **Assess performance at a glance** — See median views, publish frequency, and engagement metrics
- **Dive deeper** — Explore individual channels with detailed statistics and video history
- **Identify hidden gems** — Discover creators with strong engagement before they become expensive

### Key Metrics

The tool calculates metrics that reveal true creator value:

| Metric | Why It Matters |
|--------|----------------|
| **Median Views** | More reliable than averages — not skewed by viral outliers |
| **Views-to-Subscribers Ratio** | Shows how effectively a creator reaches their audience |
| **Publish Frequency** | Indicates consistency and reliability for ongoing partnerships |
| **Engagement Rate** | Likes and comments relative to views reveal audience connection |
| **Channel Score** | Combined metric (0-100) weighing activity, performance, and engagement |

### Who This Is For

- **Marketing teams** seeking influencer partnerships
- **Brands** looking for authentic creator collaborations
- **Agencies** managing multiple client campaigns
- **Content creators** finding collaboration partners

## Getting Started

### Requirements

- Python 3.12+
- YouTube Data API key ([Get one here](https://console.cloud.google.com/))

### Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the project directory:
   ```
   YOUTUBE_API_KEY=your_api_key_here
   ```

3. Run the application:
   ```bash
   streamlit run creator_app.py
   ```

## How It Works

1. **Search** — Enter a keyword related to your target niche
2. **Filter** — Adjust view, subscriber, and activity filters to match your criteria
3. **Review** — Browse the results table sorted by your preferred metric
4. **Explore** — Click any channel for detailed performance data and video history

## API Usage

This tool uses the YouTube Data API v3. Each search consumes API quota. The application is designed to batch requests efficiently, but be mindful of your daily quota limits when running multiple searches.

## License

MIT